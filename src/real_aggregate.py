"""Aggregate a pinned public mirror of the CFPB bulk export without storing raw narratives."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

import duckdb
import pandas as pd

from .pipeline import score_anomalies


ROOT = Path(__file__).resolve().parents[1]
MIRROR_REPOSITORY = "Mouwiya/cfpb-consumer-complaints"
MIRROR_SHA = "038f8f8b18879c9384abfee5d0b685b00c03b3cf"


def mirror_urls() -> list[str]:
    return [
        "https://huggingface.co/datasets/"
        f"{MIRROR_REPOSITORY}/resolve/{MIRROR_SHA}/data/complaints-{index:05d}.parquet"
        for index in range(67)
    ]


def _clean(column: str) -> str:
    return f"coalesce(nullif(trim(cast({column} as varchar)), ''), 'Unknown')"


def _write_real_preview(
    root: Path,
    monthly: pd.DataFrame,
    anomalies: pd.DataFrame,
    kpi: pd.DataFrame,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    monthly_total = monthly.groupby("month", as_index=False)["complaints"].sum()
    product_total = (
        monthly.groupby("product", as_index=False)["complaints"]
        .sum()
        .nlargest(8, "complaints")
        .sort_values("complaints")
    )
    if anomalies.empty:
        anomaly_plot = anomalies.copy()
    else:
        anomaly_plot = anomalies.assign(
            complaints=pd.to_numeric(anomalies["complaints"])
        ).sort_values("complaints", ascending=False).drop_duplicates(
            ["product", "issue"]
        ).head(8).sort_values("complaints")

    figures = []
    figure, axis = plt.subplots(figsize=(11.69, 8.27))
    axis.axis("off")
    row = kpi.iloc[0]
    axis.set_title("01 Executive overview", loc="left", fontsize=22, fontweight="bold")
    axis.text(
        0.04,
        0.82,
        f"Complaints\n{int(row['complaints']):,}\n\n"
        f"Complete months\n{int(row['complete_months'])}\n\n"
        f"Timely response\n{row['timely_response_rate_pct']:.2f}%",
        transform=axis.transAxes,
        fontsize=22,
        va="top",
    )
    axis.text(
        0.50,
        0.82,
        f"Narrative availability\n{row['narrative_availability_pct']:.2f}%\n\n"
        f"Detected anomalies\n{int(row['anomaly_count']):,}\n\n"
        "Company ranking is not performed\n(no customer or market-share denominator)",
        transform=axis.transAxes,
        fontsize=18,
        va="top",
    )
    figures.append(figure)

    figure, axis = plt.subplots(figsize=(11.69, 8.27))
    axis.plot(pd.to_datetime(monthly_total["month"]), monthly_total["complaints"], color="#125D98", linewidth=2.5)
    axis.set_title("02 Monthly complaint trend", loc="left", fontsize=22, fontweight="bold")
    axis.set_ylabel("Complaints")
    axis.grid(alpha=0.25)
    figure.autofmt_xdate()
    figure.tight_layout()
    figures.append(figure)

    figure, axis = plt.subplots(figsize=(11.69, 8.27))
    axis.barh(product_total["product"], product_total["complaints"], color="#2E8B57")
    axis.set_title("03 Product mix", loc="left", fontsize=22, fontweight="bold")
    axis.set_xlabel("Complaints")
    axis.tick_params(axis="y", labelsize=9)
    figure.tight_layout()
    figures.append(figure)

    figure, axis = plt.subplots(figsize=(11.69, 8.27))
    if anomaly_plot.empty:
        axis.text(0.5, 0.5, "No anomaly met the configured threshold", ha="center", va="center")
        axis.axis("off")
    else:
        labels = (
            anomaly_plot["month"].astype(str)
            + " | "
            + anomaly_plot["product"].str.slice(0, 24)
            + " | "
            + anomaly_plot["issue"].str.slice(0, 30)
        )
        axis.barh(labels, anomaly_plot["complaints"], color="#C4553D")
        axis.set_xscale("log")
        axis.set_xlabel("Complaints in flagged month (log scale)")
        axis.tick_params(axis="y", labelsize=8)
    axis.set_title("04 Product / issue review queue", loc="left", fontsize=22, fontweight="bold")
    figure.tight_layout()
    figures.append(figure)

    pdf_path = reports / "real_power_bi_preview.pdf"
    with PdfPages(pdf_path) as pdf:
        for index, figure in enumerate(figures, start=1):
            figure.savefig(reports / f"real_power_bi_preview_page_{index}.png", dpi=150)
            pdf.savefig(figure)
            plt.close(figure)


def build_real_aggregates(
    source_paths: Sequence[str], root: Path, start_date: str, end_date: str
) -> dict[str, object]:
    """Build aggregate-only marts from CFPB-compatible Parquet files."""
    database = root / "data" / "mart" / "cfpb_real_aggregate.duckdb"
    database.parent.mkdir(parents=True, exist_ok=True)
    bi = root / "bi"
    bi.mkdir(parents=True, exist_ok=True)

    with duckdb.connect(str(database)) as connection:
        parameters = [list(source_paths), start_date, end_date]
        connection.execute(
            f"""
            CREATE OR REPLACE TABLE real_monthly_product_issue AS
            SELECT
                cast(date_trunc('month', cast(date_received AS timestamp)) AS date) AS month,
                {_clean('product')} AS product,
                {_clean('issue')} AS issue,
                count(*)::BIGINT AS complaints,
                sum(CASE WHEN timely_response = 'Yes' THEN 1 ELSE 0 END)::BIGINT AS timely_count,
                sum(CASE WHEN timely_response = 'No' THEN 1 ELSE 0 END)::BIGINT AS untimely_count,
                sum(CASE
                    WHEN lower({_clean('company_response_to_consumer')}) LIKE '%monetary relief%'
                     AND lower({_clean('company_response_to_consumer')}) NOT LIKE '%non-monetary%'
                    THEN 1 ELSE 0 END)::BIGINT AS monetary_relief_count,
                sum(CASE
                    WHEN lower({_clean('company_response_to_consumer')}) LIKE '%non-monetary%'
                    THEN 1 ELSE 0 END)::BIGINT AS non_monetary_relief_count,
                sum(CASE
                    WHEN consumer_complaint_narrative IS NOT NULL
                     AND trim(cast(consumer_complaint_narrative AS varchar)) <> ''
                    THEN 1 ELSE 0 END)::BIGINT AS narrative_count
            FROM read_parquet(?)
            WHERE cast(date_received AS date) BETWEEN cast(? AS date) AND cast(? AS date)
            GROUP BY 1, 2, 3
            """,
            parameters,
        )
        connection.execute(
            f"""
            CREATE OR REPLACE TABLE real_channel_state AS
            SELECT
                cast(date_trunc('month', cast(date_received AS timestamp)) AS date) AS month,
                {_clean('submitted_via')} AS submitted_via,
                {_clean('state')} AS state,
                count(*)::BIGINT AS complaints
            FROM read_parquet(?)
            WHERE cast(date_received AS date) BETWEEN cast(? AS date) AND cast(? AS date)
            GROUP BY 1, 2, 3
            """,
            parameters,
        )
        connection.execute(
            f"""
            CREATE OR REPLACE TABLE real_company_response AS
            SELECT
                cast(date_trunc('month', cast(date_received AS timestamp)) AS date) AS month,
                {_clean('company')} AS company,
                {_clean('product')} AS product,
                {_clean('company_response_to_consumer')} AS company_response_to_consumer,
                count(*)::BIGINT AS complaints
            FROM read_parquet(?)
            WHERE cast(date_received AS date) BETWEEN cast(? AS date) AND cast(? AS date)
            GROUP BY 1, 2, 3, 4
            """,
            parameters,
        )

        monthly = connection.execute(
            "SELECT * FROM real_monthly_product_issue ORDER BY month, product, issue"
        ).df()
        channel_state = connection.execute(
            "SELECT * FROM real_channel_state ORDER BY month, submitted_via, state"
        ).df()
        company_response = connection.execute(
            "SELECT * FROM real_company_response ORDER BY month, company, product"
        ).df()
        response_summary = (
            company_response.groupby(
                ["product", "company_response_to_consumer"], as_index=False
            )["complaints"]
            .sum()
            .sort_values(
                ["complaints", "product", "company_response_to_consumer"],
                ascending=[False, True, True],
            )
            .reset_index(drop=True)
        )

        anomaly_input = monthly.copy()
        anomaly_input["month"] = pd.to_datetime(anomaly_input["month"]).dt.strftime("%Y-%m")
        anomalies = pd.DataFrame(score_anomalies(anomaly_input.to_dict("records")))
        if anomalies.empty:
            anomalies = pd.DataFrame(
                columns=[
                    *anomaly_input.columns,
                    "baseline_complaints",
                    "robust_z",
                    "anomaly_label",
                ]
            )

        complaints = int(monthly["complaints"].sum())
        timely_count = int(monthly["timely_count"].sum())
        untimely_count = int(monthly["untimely_count"].sum())
        timely_denominator = timely_count + untimely_count
        narrative_count = int(monthly["narrative_count"].sum())
        product_issue_totals = monthly.groupby(["product", "issue"])["complaints"].sum()
        channel_totals = channel_state.groupby("submitted_via")["complaints"].sum()
        kpi = pd.DataFrame(
            [
                {
                    "complaints": complaints,
                    "complete_months": int(monthly["month"].nunique()),
                    "first_month": str(monthly["month"].min()),
                    "last_month": str(monthly["month"].max()),
                    "timely_count": timely_count,
                    "timely_response_denominator": timely_denominator,
                    "timely_response_rate_pct": round(100 * timely_count / timely_denominator, 4) if timely_denominator else None,
                    "monetary_relief_count": int(monthly["monetary_relief_count"].sum()),
                    "non_monetary_relief_count": int(monthly["non_monetary_relief_count"].sum()),
                    "narrative_count": narrative_count,
                    "narrative_availability_pct": round(100 * narrative_count / complaints, 4) if complaints else None,
                    "top_product_issue_concentration_pct": round(100 * float(product_issue_totals.max()) / complaints, 4) if complaints else None,
                    "top_channel_share_pct": round(100 * float(channel_totals.max()) / complaints, 4) if complaints else None,
                    "anomaly_count": len(anomalies),
                    "analysis_start": start_date,
                    "analysis_end": end_date,
                    "source_type": "pinned third-party Parquet mirror of CFPB public bulk export",
                }
            ]
        )

        connection.register("_real_anomalies", anomalies)
        connection.register("_real_kpi", kpi)
        connection.register("_real_response_summary", response_summary)
        connection.execute("CREATE OR REPLACE TABLE real_anomaly_mart AS SELECT * FROM _real_anomalies")
        connection.execute("CREATE OR REPLACE TABLE real_kpi AS SELECT * FROM _real_kpi")
        connection.execute(
            "CREATE OR REPLACE TABLE real_response_summary AS "
            "SELECT * FROM _real_response_summary"
        )

    monthly.to_csv(bi / "real_monthly_product_issue.csv", index=False)
    channel_state.to_csv(bi / "real_channel_state.csv", index=False)
    company_response.to_csv(bi / "real_company_response.csv", index=False)
    response_summary.to_csv(bi / "real_response_summary.csv", index=False)
    anomalies.to_csv(bi / "real_anomaly_mart.csv", index=False)
    kpi.to_csv(bi / "real_kpi.csv", index=False)
    _write_real_preview(root, monthly, anomalies, kpi)

    manifest = {
        "source": "CFPB Consumer Complaint Database",
        "mirror_repository": MIRROR_REPOSITORY,
        "mirror_revision": MIRROR_SHA,
        "file_pattern": "data/complaints-00000.parquet through complaints-00066.parquet",
        "analysis_start": start_date,
        "analysis_end": end_date,
        "raw_narratives_stored": False,
        "caveat": "The official CFPB endpoint returned HTTP 403 in this environment; aggregate results use a pinned third-party conversion and should be refreshed from the official source when access is restored.",
    }
    manifest_path = root / "docs" / "real_source_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {
        "complaints": complaints,
        "complete_months": int(kpi.loc[0, "complete_months"]),
        "anomalies": len(anomalies),
        "analysis_start": start_date,
        "analysis_end": end_date,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build real aggregate CFPB marts from a pinned mirror")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--start-date", default="2023-09-01")
    parser.add_argument("--end-date", default="2026-06-30")
    args = parser.parse_args()
    result = build_real_aggregates(mirror_urls(), args.root, args.start_date, args.end_date)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
