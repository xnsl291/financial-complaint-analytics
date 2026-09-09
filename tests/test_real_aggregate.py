from pathlib import Path

import duckdb
import pandas as pd

from src.real_aggregate import build_real_aggregates


def test_real_aggregate_filters_dates_and_preserves_relief_denominators(tmp_path: Path):
    source = tmp_path / "complaints.parquet"
    pd.DataFrame(
        [
            {
                "date_received": "2023-08-31",
                "product": "Card",
                "issue": "Fee",
                "timely_response": "Yes",
                "company_response_to_consumer": "Closed with explanation",
                "consumer_complaint_narrative": None,
                "submitted_via": "Web",
                "state": "CA",
                "company": "A",
            },
            {
                "date_received": "2023-09-10",
                "product": "Card",
                "issue": "Fee",
                "timely_response": "Yes",
                "company_response_to_consumer": "Closed with monetary relief",
                "consumer_complaint_narrative": "fee charged",
                "submitted_via": "Web",
                "state": "CA",
                "company": "A",
            },
            {
                "date_received": "2023-09-11",
                "product": "Card",
                "issue": "Fee",
                "timely_response": "No",
                "company_response_to_consumer": "Closed with non-monetary relief",
                "consumer_complaint_narrative": "late fee",
                "submitted_via": "Phone",
                "state": "NY",
                "company": "B",
            },
            {
                "date_received": "2023-10-01",
                "product": "Mortgage",
                "issue": "Payment",
                "timely_response": "Unknown",
                "company_response_to_consumer": "Closed with explanation",
                "consumer_complaint_narrative": "",
                "submitted_via": "Web",
                "state": None,
                "company": "C",
            },
        ]
    ).to_parquet(source, index=False)

    summary = build_real_aggregates(
        [str(source)], tmp_path / "out", "2023-09-01", "2023-10-31"
    )

    assert summary["complaints"] == 3
    assert summary["complete_months"] == 2
    kpi = pd.read_csv(tmp_path / "out" / "bi" / "real_kpi.csv").iloc[0]
    assert kpi["timely_response_denominator"] == 2
    assert kpi["monetary_relief_count"] == 1
    assert kpi["non_monetary_relief_count"] == 1
    assert kpi["narrative_count"] == 2


def test_real_aggregate_persists_small_duckdb_marts_and_bi_exports(tmp_path: Path):
    source = tmp_path / "complaints.parquet"
    pd.DataFrame(
        [
            {
                "date_received": "2024-01-01",
                "product": "Card",
                "issue": "Fee",
                "timely_response": "Yes",
                "company_response_to_consumer": "Closed with explanation",
                "consumer_complaint_narrative": None,
                "submitted_via": "Web",
                "state": "CA",
                "company": "A",
            }
        ]
    ).to_parquet(source, index=False)

    root = tmp_path / "out"
    build_real_aggregates([str(source)], root, "2024-01-01", "2024-01-31")

    database = root / "data" / "mart" / "cfpb_real_aggregate.duckdb"
    with duckdb.connect(str(database), read_only=True) as connection:
        tables = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
    assert {
        "real_monthly_product_issue",
        "real_channel_state",
        "real_company_response",
        "real_response_summary",
        "real_anomaly_mart",
        "real_kpi",
    }.issubset(tables)
    assert (root / "bi" / "real_monthly_product_issue.csv").exists()
    response_summary = pd.read_csv(root / "bi" / "real_response_summary.csv")
    assert response_summary.to_dict("records") == [
        {
            "product": "Card",
            "company_response_to_consumer": "Closed with explanation",
            "complaints": 1,
        }
    ]
    assert (root / "bi" / "real_anomaly_mart.csv").exists()
    assert len(list((root / "reports").glob("real_power_bi_preview_page_*.png"))) == 4
    assert (root / "reports" / "real_power_bi_preview.pdf").exists()
