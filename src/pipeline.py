"""Deterministic, local CFPB complaint analytics pipeline (no LLM decisions)."""
from __future__ import annotations

import argparse
import calendar
import csv
import json
import math
import re
import statistics
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import duckdb

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WEIGHTS = {"volume": 0.30, "growth": 0.25, "untimely": 0.20, "relief": 0.15, "persistence": 0.10}
TAXONOMY_MONTH_BOUNDARY = date(2023, 8, 1)
STOPWORDS = {"a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "i", "in", "is", "it", "my", "of", "on", "or", "that", "the", "this", "to", "was", "with", "you", "your"}


def compute_complete_cutoff(today: date | None = None) -> date:
    """Last day of the month two calendar months before ``today``."""
    today = today or date.today()
    month_index = today.year * 12 + today.month - 3
    year, month0 = divmod(month_index, 12)
    month = month0 + 1
    return date(year, month, calendar.monthrange(year, month)[1])


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _text(value: Any, default: str = "Unknown") -> str:
    value = str(value or "").strip()
    return value if value else default


def deduplicate_and_normalize(rows: Iterable[dict[str, Any]], cutoff: date) -> list[dict[str, Any]]:
    """Normalize official headers, keep first Complaint ID, and exclude data-lag months."""
    out, seen = [], set()
    aliases = {"Complaint ID": "complaint_id", "Date received": "date_received", "Date sent to company": "date_sent_to_company", "Company": "company", "Product": "product", "Sub-product": "sub_product", "Issue": "issue", "Sub-issue": "sub_issue", "Company public response": "company_public_response", "Company response to consumer": "company_response_to_consumer", "Timely response?": "timely_response", "Consumer disputed?": "consumer_disputed", "Submitted via": "submitted_via", "Date company response": "date_company_response", "State": "state", "ZIP code": "zip_code", "Tags": "tags", "Consumer complaint narrative": "narrative"}
    for raw in rows:
        complaint_id = _text(raw.get("Complaint ID") or raw.get("complaint_id"), "")
        received = _parse_date(raw.get("Date received") or raw.get("date_received"))
        if not complaint_id or complaint_id in seen or received is None or received > cutoff:
            continue
        seen.add(complaint_id)
        item = {target: _text(raw.get(source) if source in raw else raw.get(target)) for source, target in aliases.items()}
        item["complaint_id"] = complaint_id
        item["date_received"] = received
        item["date_sent_to_company"] = _parse_date(raw.get("Date sent to company") or raw.get("date_sent_to_company"))
        item["date_company_response"] = _parse_date(raw.get("Date company response") or raw.get("date_company_response"))
        item["month"] = received.strftime("%Y-%m")
        item["taxonomy_version"] = "pre_2023_08_update" if received < TAXONOMY_MONTH_BOUNDARY else "post_2023_08_update"
        item["timely_response"] = _text(raw.get("Timely response?") or raw.get("timely_response"), "")
        item["narrative_available"] = 0 if item["narrative"] == "Unknown" else 1
        if item["date_sent_to_company"] and item["date_company_response"]:
            item["days_to_company"] = (item["date_company_response"] - item["date_sent_to_company"]).days
        else:
            item["days_to_company"] = None
        out.append(item)
    return out


def month_metrics(rows: list[dict[str, Any]], aggregate_only: bool = False) -> list[dict[str, Any]]:
    if aggregate_only:
        eligible = [r for r in rows if _text(r.get("timely_response"), "") in {"Yes", "No"}]
        timely = sum(_text(r.get("timely_response"), "") == "Yes" for r in eligible)
        return [{"timely_response_denominator": len(eligible), "timely_response_rate_pct": round(100 * timely / len(eligible), 2) if eligible else None}]
    values = sorted(rows, key=lambda r: r["month"])
    prior = {r["month"]: r["complaints"] for r in values}
    result = []
    for r in values:
        year, month = map(int, r["month"].split("-"))
        previous = f"{year - 1 if month == 1 else year:04d}-{12 if month == 1 else month - 1:02d}"
        yoy = f"{year - 1:04d}-{month:02d}"
        item = dict(r)
        item["mom_growth_pct"] = round(100 * (r["complaints"] - prior[previous]) / prior[previous], 2) if prior.get(previous) else None
        item["yoy_growth_pct"] = round(100 * (r["complaints"] - prior[yoy]) / prior[yoy], 2) if prior.get(yoy) else None
        result.append(item)
    return result


def score_anomalies(monthly: list[dict[str, Any]], min_volume: int = 20) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in sorted(monthly, key=lambda x: (x["product"], x["issue"], x["month"])):
        grouped[(row["product"], row["issue"])].append(row)
    results = []
    for _, series in grouped.items():
        for idx, row in enumerate(series):
            baseline = [x["complaints"] for x in series[max(0, idx - 3):idx]]
            if row["complaints"] < min_volume or len(baseline) < 2:
                continue
            median = statistics.median(baseline)
            mad = statistics.median([abs(x - median) for x in baseline])
            z = 0.0 if mad == 0 and row["complaints"] <= median else (row["complaints"] - median) / max(1.4826 * mad, 1)
            if z >= 3.5:
                future = [x["complaints"] for x in series[idx + 1:idx + 3]]
                label = "persistent" if any(x >= max(min_volume, median * 1.5) for x in future) else "spike"
                results.append({**row, "baseline_complaints": median, "robust_z": round(z, 3), "anomaly_label": label})
    return results


def score_priority(item: dict[str, Any], weights: dict[str, float] = DEFAULT_WEIGHTS, maxima: dict[str, float] | None = None) -> dict[str, Any]:
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-9):
        raise ValueError("priority weights must sum to 1")
    maxima = maxima or {"volume": max(item.get("volume", 0), 1), "growth": 100, "untimely": 100, "relief": 100, "persistence": 12}
    mapping = {"volume": "volume", "growth": "growth_pct", "untimely": "untimely_share_pct", "relief": "relief_share_pct", "persistence": "persistence_months"}
    components = {key: min(max(float(item.get(field, 0) or 0) / max(float(maxima.get(key, 1)), 1), 0), 1) for key, field in mapping.items()}
    return {**item, **{f"normalized_{k}": round(v, 6) for k, v in components.items()}, "priority_score": round(sum(weights[k] * components[k] for k in weights), 6)}


def tfidf_keywords(narratives: list[str], min_df: int = 2) -> list[dict[str, Any]]:
    docs = []
    for text in narratives:
        words = [x for x in re.findall(r"[a-z]{2,}", text.lower()) if x not in STOPWORDS]
        docs.append([" ".join(words[i:i + n]) for n in (1, 2) for i in range(len(words) - n + 1)])
    df = Counter(term for doc in docs for term in set(doc))
    scores: Counter[str] = Counter()
    for doc in docs:
        counts = Counter(doc)
        for term, count in counts.items():
            if df[term] >= min_df:
                scores[term] += (count / max(len(doc), 1)) * math.log((1 + len(docs)) / (1 + df[term])) + 1
    return [{"term": term, "document_frequency": df[term], "tfidf_score": round(score, 6)} for term, score in sorted(scores.items(), key=lambda x: (-x[1], x[0]))]


def make_demo_rows() -> list[dict[str, str]]:
    rows = []
    specs = [("2023-09-15", "Credit card", "Late fee", 8), ("2024-01-15", "Mortgage", "Payment trouble", 10), ("2024-02-15", "Mortgage", "Payment trouble", 11), ("2024-03-15", "Mortgage", "Payment trouble", 31), ("2024-03-20", "Credit card", "Late fee", 16), ("2025-01-15", "Crypto asset", "Fraud", 14), ("2025-02-15", "Crypto asset", "Fraud", 17), ("2025-03-15", "Crypto asset", "Fraud", 38), ("2025-04-15", "Crypto asset", "Fraud", 99)]
    n = 1
    for received, product, issue, count in specs:
        for i in range(count):
            response = ("Closed with monetary relief" if i % 5 == 0 else "Closed with non-monetary relief" if i % 7 == 0 else "Closed with explanation")
            rows.append({"Complaint ID": str(n), "Date received": received, "Date sent to company": received, "Date company response": received, "Company": "Demo Finance " + str(i % 3 + 1), "Product": product, "Sub-product": "Unknown", "Issue": issue, "Sub-issue": "Unknown", "Company response to consumer": response, "Timely response?": "No" if i % 6 == 0 else "Yes", "Submitted via": "Web", "State": "CA" if i % 2 else "NY", "Consumer complaint narrative": "merchant dispute delayed refund" if product == "Credit card" else "payment delayed customer concern"})
            n += 1
    rows.append(dict(rows[0]))  # intentional duplicate for the quality mart
    return rows


def _csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("\n", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def _create_preview(root: Path, trend: list[dict[str, Any]], anomalies: list[dict[str, Any]], kpi: dict[str, Any]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    reports = root / "reports"; reports.mkdir(parents=True, exist_ok=True)
    titles = ["1. Executive KPI", "2. Monthly trend", "3. Product / issue priority", "4. Historical narrative & data quality"]
    pages = []
    for idx, title in enumerate(titles, 1):
        fig, ax = plt.subplots(figsize=(11.69, 8.27)); fig.patch.set_facecolor("#F7FAFC"); ax.set_title(title, loc="left", fontsize=20, fontweight="bold")
        if idx == 1:
            ax.bar(["Complaints", "Timely %", "Anomalies"], [kpi["complaints"], kpi["timely_response_rate_pct"], kpi["anomaly_count"]], color=["#155E75", "#0F766E", "#DC2626"])
        elif idx == 2:
            ax.plot([x["month"] for x in trend], [x["complaints"] for x in trend], marker="o", color="#155E75"); ax.tick_params(axis="x", rotation=45)
        elif idx == 3:
            labels = [f'{x["product"]}: {x["issue"]}' for x in anomalies] or ["No qualified anomaly"]
            vals = [x["complaints"] for x in anomalies] or [0]; ax.barh(labels, vals, color="#DC2626")
        else:
            ax.text(.03, .75, f"Historical narrative availability: {kpi['narrative_availability_pct']:.1f}%\nNew narrative publication ceased: 2026-08-14\nAutomated compliance judgment: not performed", transform=ax.transAxes, fontsize=16, va="top")
            ax.axis("off")
        ax.grid(axis="y", alpha=.2); fig.tight_layout(); png = reports / f"power_bi_preview_page_{idx}.png"; fig.savefig(png, dpi=150); pages.append(fig); plt.close(fig)
    from matplotlib.backends.backend_pdf import PdfPages
    with PdfPages(reports / "power_bi_preview.pdf") as pdf:
        for idx, title in enumerate(titles, 1):
            image = plt.imread(reports / f"power_bi_preview_page_{idx}.png")
            fig, ax = plt.subplots(figsize=(11.69, 8.27)); ax.imshow(image); ax.axis("off"); pdf.savefig(fig); plt.close(fig)


def _run_rows(root: Path, raw: list[dict[str, Any]], snapshot_date: str) -> dict[str, Any]:
    """Build staging, marts, exports, and previews from an already-preserved raw snapshot."""
    for name in ("data/raw", "data/staging", "data/mart", "bi", "reports"):
        (root / name).mkdir(parents=True, exist_ok=True)
    cutoff = compute_complete_cutoff(date.fromisoformat(snapshot_date))
    clean = deduplicate_and_normalize(raw, cutoff); _csv(root / "data/staging/complaints_normalized.csv", clean)
    db = root / "data/mart/complaints.duckdb"; con = duckdb.connect(str(db)); con.execute("DROP TABLE IF EXISTS fact_complaints")
    con.execute("CREATE TABLE fact_complaints (complaint_id VARCHAR, date_received DATE, month VARCHAR, company VARCHAR, product VARCHAR, issue VARCHAR, company_response_to_consumer VARCHAR, timely_response VARCHAR, submitted_via VARCHAR, state VARCHAR, narrative VARCHAR, narrative_available INTEGER, days_to_company INTEGER, taxonomy_version VARCHAR)")
    con.executemany("INSERT INTO fact_complaints VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", [(r["complaint_id"], r["date_received"], r["month"], r["company"], r["product"], r["issue"], r["company_response_to_consumer"], r["timely_response"], r["submitted_via"], r["state"], r["narrative"], r["narrative_available"], r["days_to_company"], r["taxonomy_version"]) for r in clean])
    con.execute("CREATE OR REPLACE TABLE dim_date AS SELECT DISTINCT date_received, month, year(date_received) AS year, month(date_received) AS month_number FROM fact_complaints")
    con.execute("CREATE OR REPLACE TABLE dim_product AS SELECT DISTINCT product, issue, taxonomy_version FROM fact_complaints")
    con.execute("CREATE OR REPLACE TABLE dim_company AS SELECT DISTINCT company FROM fact_complaints")
    trend = [dict(zip([d[0] for d in con.description], row)) for row in con.execute("SELECT month, count(*) AS complaints, avg(CASE WHEN timely_response='Yes' THEN 100.0 WHEN timely_response='No' THEN 0 END) AS timely_response_rate_pct FROM fact_complaints GROUP BY 1 ORDER BY 1").fetchall()]
    trend = month_metrics(trend)
    prod_issue = [dict(zip([d[0] for d in con.description], row)) for row in con.execute("SELECT month, product, issue, count(*) AS complaints FROM fact_complaints GROUP BY 1,2,3 ORDER BY 2,3,1").fetchall()]
    anomalies = score_anomalies(prod_issue, min_volume=20)
    response = [dict(zip([d[0] for d in con.description], row)) for row in con.execute("SELECT company_response_to_consumer AS response_category, count(*) AS complaints FROM fact_complaints GROUP BY 1 ORDER BY 2 DESC").fetchall()]
    keyword = tfidf_keywords([r["narrative"] for r in clean if r["narrative_available"]], min_df=2)
    total = len(clean); timely = [r for r in clean if r["timely_response"] in {"Yes", "No"}]
    monetary = sum("monetary relief" in r["company_response_to_consumer"].lower() and "non-monetary" not in r["company_response_to_consumer"].lower() for r in clean)
    non_monetary = sum("non-monetary relief" in r["company_response_to_consumer"].lower() for r in clean)
    product_issue = Counter((r["product"], r["issue"]) for r in clean)
    channels, states = Counter(r["submitted_via"] for r in clean), Counter(r["state"] for r in clean)
    kpi = {"complaints": total, "timely_response_rate_pct": round(100 * sum(r["timely_response"] == "Yes" for r in timely) / len(timely), 2), "timely_response_denominator": len(timely), "avg_days_to_company": round(sum(r["days_to_company"] or 0 for r in clean) / total, 2), "monetary_relief_share_pct": round(100 * monetary / total, 2), "non_monetary_relief_share_pct": round(100 * non_monetary / total, 2), "top_product_issue_concentration_pct": round(100 * max(product_issue.values()) / total, 2), "top_channel_share_pct": round(100 * max(channels.values()) / total, 2), "top_state_share_pct": round(100 * max(states.values()) / total, 2), "narrative_availability_pct": round(100 * sum(r["narrative_available"] for r in clean) / total, 2), "anomaly_count": len(anomalies), "complete_month_cutoff": cutoff.isoformat()}
    quality = [{"raw_rows": len(raw), "normalized_rows": len(clean), "duplicate_removed": len(raw) - len({r.get("Complaint ID") or r.get("complaint_id") for r in raw}), "invalid_or_lag_excluded": len(raw) - len(clean) - (len(raw) - len({r.get("Complaint ID") or r.get("complaint_id") for r in raw})), "snapshot_date": snapshot_date, "cutoff": cutoff.isoformat()}]
    con.execute("CREATE OR REPLACE TABLE monthly_trend AS SELECT * FROM (SELECT month, count(*) complaints FROM fact_complaints GROUP BY 1)")
    con.execute("CREATE OR REPLACE TABLE response_mart AS SELECT company_response_to_consumer, count(*) complaints FROM fact_complaints GROUP BY 1")
    con.execute("CREATE OR REPLACE TABLE anomaly_mart (month VARCHAR, product VARCHAR, issue VARCHAR, complaints INTEGER, baseline_complaints DOUBLE, robust_z DOUBLE, anomaly_label VARCHAR)")
    con.executemany("INSERT INTO anomaly_mart VALUES (?, ?, ?, ?, ?, ?, ?)", [(r["month"], r["product"], r["issue"], r["complaints"], r["baseline_complaints"], r["robust_z"], r["anomaly_label"]) for r in anomalies])
    con.execute("CREATE OR REPLACE TABLE keyword_mart (term VARCHAR, document_frequency INTEGER, tfidf_score DOUBLE)")
    con.executemany("INSERT INTO keyword_mart VALUES (?, ?, ?)", [(r["term"], r["document_frequency"], r["tfidf_score"]) for r in keyword])
    con.execute("CREATE OR REPLACE TABLE kpi_table AS SELECT ?::INTEGER AS complaints, ?::DOUBLE AS timely_response_rate_pct, ?::INTEGER AS anomaly_count", [total, kpi["timely_response_rate_pct"], len(anomalies)])
    con.execute("CREATE OR REPLACE TABLE quality_table AS SELECT ?::INTEGER AS raw_rows, ?::INTEGER AS normalized_rows", [len(raw), len(clean)])
    sql_count = con.execute("SELECT count(*) FROM fact_complaints").fetchone()[0]; con.close()
    fact_bi = [{k: (v.isoformat() if isinstance(v, date) else v) for k, v in r.items()} for r in clean]
    dates = list({(r["date_received"].isoformat(), r["month"]) for r in clean})
    products = list({(r["product"], r["issue"], r["taxonomy_version"]) for r in clean})
    companies = list({r["company"] for r in clean})
    channel_state = [{"submitted_via": key[0], "state": key[1], "complaints": value} for key, value in Counter((r["submitted_via"], r["state"]) for r in clean).items()]
    _csv(root / "bi/fact_complaints.csv", fact_bi); _csv(root / "bi/dim_date.csv", [{"date_received": x[0], "month": x[1]} for x in dates]); _csv(root / "bi/dim_product.csv", [{"product": x[0], "issue": x[1], "taxonomy_version": x[2]} for x in products]); _csv(root / "bi/dim_company.csv", [{"company": x} for x in companies]); _csv(root / "bi/monthly_trend.csv", trend); _csv(root / "bi/response_mart.csv", response); _csv(root / "bi/anomaly_mart.csv", anomalies); _csv(root / "bi/keyword_mart.csv", keyword); _csv(root / "bi/channel_state_mart.csv", channel_state); _csv(root / "bi/kpi_table.csv", [kpi]); _csv(root / "bi/quality_table.csv", quality)
    (root / "bi/bi_schema.json").write_text(json.dumps({"exports": ["fact_complaints.csv", "dim_date.csv", "dim_product.csv", "dim_company.csv", "monthly_trend.csv", "response_mart.csv", "anomaly_mart.csv", "keyword_mart.csv", "channel_state_mart.csv", "kpi_table.csv", "quality_table.csv"], "grain": "one complaint in fact_complaints; no company quality ranking"}, ensure_ascii=False, indent=2), encoding="utf-8")
    _create_preview(root, trend, anomalies, kpi)
    return {"reconciled": total == sql_count, "counts": {"fact_complaints": total, "raw_rows": len(raw), "preview_pages": 4}, "cutoff": cutoff.isoformat()}


def run_demo(root: Path = ROOT) -> dict[str, Any]:
    raw = make_demo_rows()
    (root / "data/raw").mkdir(parents=True, exist_ok=True)
    _csv(root / "data/raw/demo_complaints.csv", raw)
    return _run_rows(root, raw, "2025-05-15")


def build_api_url(row_cap: int, analysis_end: str) -> str:
    """Build the documented CFPB search query with explicit date bounds."""
    query = urllib.parse.urlencode(
        {
            "date_received_min": "2023-09-01",
            "date_received_max": analysis_end,
            "field": "all",
            "format": "json",
            "no_aggs": "true",
            "size": min(max(int(row_cap), 1), 500),
            "sort": "created_date_desc",
        }
    )
    return "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/?" + query


def fetch_official(root: Path, row_cap: int, snapshot_date: str) -> dict[str, Any]:
    """Bounded official API retrieval; raw response stays under ignored data/raw."""
    cutoff = compute_complete_cutoff(date.fromisoformat(snapshot_date)).isoformat()
    url = build_api_url(row_cap, cutoff)
    request = urllib.request.Request(url, headers={"User-Agent": "financial-complaint-analytics/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    hits = payload.get("hits", {}).get("hits", payload.get("results", []))
    rows = [x.get("_source", x) for x in hits][:row_cap]
    if not isinstance(rows, list) or not rows:
        raise RuntimeError("official CFPB API returned no parsable rows")
    (root / "data/raw").mkdir(parents=True, exist_ok=True)
    _csv(root / "data/raw" / f"cfpb_{snapshot_date}.csv", rows)
    return {"status": "ok", "rows": len(rows), "snapshot_date": snapshot_date, "url": url}


def main() -> None:
    parser = argparse.ArgumentParser(description="CFPB financial complaint analytics")
    parser.add_argument("command", choices=["ingest", "validate", "transform", "analyze", "export-bi", "verify", "all"])
    parser.add_argument("--demo", action="store_true", help="use deterministic bundled fixture")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--row-cap", type=int, default=500)
    parser.add_argument("--snapshot-date", default=date.today().isoformat())
    args = parser.parse_args()
    if args.demo:
        result = run_demo(args.root)
    elif args.command == "ingest":
        result = fetch_official(args.root, args.row_cap, args.snapshot_date)
    elif args.command == "all":
        status = fetch_official(args.root, args.row_cap, args.snapshot_date)
        raw_path = args.root / "data/raw" / f"cfpb_{args.snapshot_date}.csv"
        with raw_path.open(encoding="utf-8-sig", newline="") as handle:
            result = {**status, **_run_rows(args.root, list(csv.DictReader(handle)), args.snapshot_date)}
    else:
        raise SystemExit("Full mode begins with ingest; run `ingest` first or use deterministic `--demo`.")
    print(json.dumps({"command": args.command, **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()
