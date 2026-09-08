-- DuckDB mart contract. The executable pipeline materializes these tables.
CREATE TABLE fact_complaints (
  complaint_id VARCHAR, date_received DATE, month VARCHAR, company VARCHAR,
  product VARCHAR, issue VARCHAR, company_response_to_consumer VARCHAR,
  timely_response VARCHAR, submitted_via VARCHAR, state VARCHAR, narrative VARCHAR,
  narrative_available INTEGER, days_to_company INTEGER, taxonomy_version VARCHAR
);
CREATE TABLE dim_date AS SELECT DISTINCT date_received, month FROM fact_complaints;
CREATE TABLE dim_product AS SELECT DISTINCT product, issue, taxonomy_version FROM fact_complaints;
CREATE TABLE dim_company AS SELECT DISTINCT company FROM fact_complaints;
CREATE TABLE monthly_trend AS SELECT month, count(*) AS complaints FROM fact_complaints GROUP BY 1;
CREATE TABLE response_mart AS SELECT company_response_to_consumer, count(*) AS complaints FROM fact_complaints GROUP BY 1;
CREATE TABLE anomaly_mart (month VARCHAR, product VARCHAR, issue VARCHAR, complaints INTEGER, baseline_complaints DOUBLE, robust_z DOUBLE, anomaly_label VARCHAR);
CREATE TABLE keyword_mart (term VARCHAR, document_frequency INTEGER, tfidf_score DOUBLE);
CREATE TABLE kpi_table (complaints INTEGER, timely_response_rate_pct DOUBLE, anomaly_count INTEGER);
CREATE TABLE quality_table (raw_rows INTEGER, normalized_rows INTEGER);
