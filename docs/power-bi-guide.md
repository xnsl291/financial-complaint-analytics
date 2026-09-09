# Power BI 모델과 대시보드 가이드

## 모델

중심 fact는 `fact_complaints`(민원 1건)이다. `dim_date[date_received]` → fact 날짜, `dim_product[product, issue, taxonomy_version]` → fact 분류, `dim_company[company]` → fact 회사 관계를 단방향 1:*로 설정한다. `monthly_trend`, `response_mart`, `anomaly_mart`, `keyword_mart`, `kpi_table`, `quality_table`은 집계 시각화용 독립 마트로 가져온다. 회사 차원은 분모 부재 때문에 품질 순위 용도로 사용하지 않는다.

실데이터 보고서는 원문을 가져오지 않고 `real_` 접두사의 집계 CSV만 사용한다. 실행 시 생성되는 `real_monthly_product_issue`를 추세와 이상징후의 중심으로 쓰고, `real_channel_state`, `real_company_response`, `real_anomaly_mart`, `real_kpi`를 독립 집계 마트로 가져온다. 저장소에는 검토 가능한 크기의 `real_response_summary`를 대신 공개한다. 집계 수준이 서로 다르므로 테이블 간 다대다 관계를 만들지 않고 각 페이지에 필요한 마트를 직접 사용한다.

## Korean DAX measures

```DAX
민원 건수 = DISTINCTCOUNT(fact_complaints[complaint_id])
적기 응답 건수 = CALCULATE([민원 건수], fact_complaints[timely_response] = "Yes")
적기 응답 분모 = CALCULATE([민원 건수], fact_complaints[timely_response] IN {"Yes", "No"})
적기 응답률 = DIVIDE([적기 응답 건수], [적기 응답 분모])
전월 대비 = DIVIDE([민원 건수] - CALCULATE([민원 건수], DATEADD(dim_date[date_received], -1, MONTH)), CALCULATE([민원 건수], DATEADD(dim_date[date_received], -1, MONTH)))
전년동월 대비 = DIVIDE([민원 건수] - CALCULATE([민원 건수], DATEADD(dim_date[date_received], -1, YEAR)), CALCULATE([민원 건수], DATEADD(dim_date[date_received], -1, YEAR)))
```

What-if 매개변수는 Volume 0.30, Growth 0.25, Untimely 0.20, Relief 0.15, Persistence 0.10에서 시작한다. 매개변수 변경 뒤에는 가중치 합계가 1인지 검증하고, 점수는 절대 위험판정이 아니라 검토 순서만 조정한다.

## 4개 페이지

1. 경영 KPI: 민원 수, 적기응답률, 이상치 수, 완전월 cutoff
2. 추세: 월별 민원, MoM, YoY 및 taxonomy 경계
3. 운영 검토: product/issue 이상치와 priority 구성요소
4. 역사적 텍스트와 품질: 정책 변경 전 TF-IDF 키워드, narrative 존재율, 중복 및 제외 품질

실데이터 정적 미리보기는 같은 네 자리를 경영 KPI, 월별 추세, 상품 구성, 상품 및 이슈 검토 큐로 바꿔 구성했다. `reports/real_power_bi_preview_page_1.png`부터 `4.png`까지에서 확인할 수 있다.
