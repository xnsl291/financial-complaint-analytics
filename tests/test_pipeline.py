import csv
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from src.pipeline import (
    build_api_url,
    compute_complete_cutoff,
    deduplicate_and_normalize,
    make_demo_rows,
    month_metrics,
    run_demo,
    score_anomalies,
    score_priority,
    tfidf_keywords,
)


class FinancialComplaintPipelineTests(unittest.TestCase):
    """Contracts: a removal of each named behavior below must fail its test."""

    def test_duplicate_id_keeps_one_normalized_record(self):
        rows = [
            {"Complaint ID": "7", "Date received": "2024-01-02", "Product": " ", "Issue": "Late fee"},
            {"Complaint ID": "7", "Date received": "2024-01-03", "Product": "Credit card", "Issue": "Late fee"},
        ]
        cleaned = deduplicate_and_normalize(rows, date(2024, 6, 30))
        self.assertEqual(1, len(cleaned))
        self.assertEqual("Unknown", cleaned[0]["product"])
        self.assertEqual(date(2024, 1, 2), cleaned[0]["date_received"])

    def test_date_parsing_discards_invalid_and_incomplete_months(self):
        rows = [
            {"Complaint ID": "1", "Date received": "02/15/2024", "Product": "Mortgage"},
            {"Complaint ID": "2", "Date received": "bad-date", "Product": "Mortgage"},
            {"Complaint ID": "3", "Date received": "2024-05-01", "Product": "Mortgage"},
        ]
        cleaned = deduplicate_and_normalize(rows, date(2024, 4, 30))
        self.assertEqual(["1"], [r["complaint_id"] for r in cleaned])

    def test_complete_cutoff_is_last_day_two_months_before_today(self):
        self.assertEqual(date(2024, 1, 31), compute_complete_cutoff(date(2024, 3, 1)))
        self.assertEqual(date(2024, 2, 29), compute_complete_cutoff(date(2024, 4, 30)))

    def test_taxonomy_boundary_is_retained_when_product_changes(self):
        rows = [
            {"Complaint ID": "1", "Date received": "2023-07-31", "Product": "Virtual currency", "Issue": "Other"},
            {"Complaint ID": "2", "Date received": "2023-08-01", "Product": "Crypto asset", "Issue": "Other"},
        ]
        cleaned = deduplicate_and_normalize(rows, date(2023, 8, 31))
        self.assertEqual(["pre_2023_08_update", "post_2023_08_update"], [r["taxonomy_version"] for r in cleaned])

    def test_official_api_url_uses_date_filters_and_bounded_size(self):
        url = build_api_url(900, "2026-07-31")
        self.assertIn("date_received_min=2023-09-01", url)
        self.assertIn("date_received_max=2026-07-31", url)
        self.assertIn("no_aggs=true", url)
        self.assertIn("size=500", url)

    def test_mom_and_yoy_use_literal_monthly_examples(self):
        metrics = month_metrics([
            {"month": "2023-01", "complaints": 100},
            {"month": "2024-01", "complaints": 120},
            {"month": "2024-02", "complaints": 150},
        ])
        by_month = {m["month"]: m for m in metrics}
        self.assertAlmostEqual(25.0, by_month["2024-02"]["mom_growth_pct"])
        self.assertAlmostEqual(20.0, by_month["2024-01"]["yoy_growth_pct"])

    def test_timely_rate_uses_only_records_with_timely_flag(self):
        rows = [
            {"company_response_to_consumer": "Closed with explanation", "timely_response": "Yes"},
            {"company_response_to_consumer": "Closed with monetary relief", "timely_response": "No"},
            {"company_response_to_consumer": "Closed with non-monetary relief", "timely_response": ""},
        ]
        metrics = month_metrics(rows, aggregate_only=True)[0]
        self.assertAlmostEqual(50.0, metrics["timely_response_rate_pct"])
        self.assertEqual(2, metrics["timely_response_denominator"])

    def test_anomaly_needs_minimum_volume(self):
        monthly = [
            {"month": "2024-01", "product": "Card", "issue": "Fee", "complaints": 4},
            {"month": "2024-02", "product": "Card", "issue": "Fee", "complaints": 4},
            {"month": "2024-03", "product": "Card", "issue": "Fee", "complaints": 40},
        ]
        result = score_anomalies(monthly, min_volume=50)
        self.assertEqual([], result)

    def test_priority_score_uses_normalized_components_and_unit_weights(self):
        item = score_priority({"volume": 100, "growth_pct": 20, "untimely_share_pct": 10, "relief_share_pct": 30, "persistence_months": 2},
                              {"volume": 0.30, "growth": 0.25, "untimely": 0.20, "relief": 0.15, "persistence": 0.10},
                              {"volume": 200, "growth": 40, "untimely": 20, "relief": 60, "persistence": 4})
        self.assertAlmostEqual(0.5, item["priority_score"])
        with self.assertRaises(ValueError):
            score_priority({"volume": 1}, {"volume": 0.8}, {"volume": 1})

    def test_tfidf_returns_interpretable_ngram_from_narratives(self):
        keywords = tfidf_keywords([
            "merchant dispute delayed refund",
            "merchant dispute chargeback denied",
            "mortgage payment delayed",
        ], min_df=2)
        terms = {k["term"] for k in keywords}
        self.assertIn("merchant dispute", terms)
        self.assertNotIn("the", terms)

    def test_sql_and_python_kpis_reconcile_and_bi_schema_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_demo(Path(tmp))
            self.assertTrue(result["reconciled"])
            schema = json.loads((Path(tmp) / "bi" / "bi_schema.json").read_text(encoding="utf-8"))
            self.assertIn("fact_complaints.csv", schema["exports"])
            with (Path(tmp) / "bi" / "monthly_trend.csv").open(encoding="utf-8") as f:
                self.assertIn("complaints", next(csv.DictReader(f)).keys())

    def test_demo_end_to_end_creates_four_page_preview(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_demo(Path(tmp))
            self.assertGreater(result["counts"]["fact_complaints"], 0)
            self.assertEqual(4, result["counts"]["preview_pages"])
            self.assertTrue((Path(tmp) / "reports" / "power_bi_preview.pdf").exists())


if __name__ == "__main__":
    unittest.main()
