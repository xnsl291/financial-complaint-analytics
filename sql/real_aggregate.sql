-- Reviewer-facing version of the core query in src/real_aggregate.py.
-- `source_files`, `start_date`, and `end_date` are supplied by the pipeline.

SELECT
    CAST(date_trunc('month', CAST(date_received AS TIMESTAMP)) AS DATE) AS month,
    COALESCE(NULLIF(TRIM(CAST(product AS VARCHAR)), ''), 'Unknown') AS product,
    COALESCE(NULLIF(TRIM(CAST(issue AS VARCHAR)), ''), 'Unknown') AS issue,
    COUNT(*)::BIGINT AS complaints,
    SUM(CASE WHEN timely_response = 'Yes' THEN 1 ELSE 0 END)::BIGINT AS timely_count,
    SUM(CASE WHEN timely_response = 'No' THEN 1 ELSE 0 END)::BIGINT AS untimely_count,
    SUM(CASE
        WHEN LOWER(company_response_to_consumer) LIKE '%monetary relief%'
         AND LOWER(company_response_to_consumer) NOT LIKE '%non-monetary%'
        THEN 1 ELSE 0 END)::BIGINT AS monetary_relief_count,
    SUM(CASE
        WHEN LOWER(company_response_to_consumer) LIKE '%non-monetary%'
        THEN 1 ELSE 0 END)::BIGINT AS non_monetary_relief_count
FROM read_parquet(source_files)
WHERE CAST(date_received AS DATE) BETWEEN start_date AND end_date
GROUP BY 1, 2, 3;
