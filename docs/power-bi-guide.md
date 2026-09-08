# Power BI 모델·대시보드 가이드

## 모델

중심 fact는 `fact_complaints`(민원 1건)이다. `dim_date[date_received]` → fact 날짜, `dim_product[product, issue, taxonomy_version]` → fact 분류, `dim_company[company]` → fact 회사 관계를 단방향 1:*로 설정한다. `monthly_trend`, `response_mart`, `anomaly_mart`, `keyword_mart`, `kpi_table`, `quality_table`은 집계 시각화용 독립 마트로 가져온다. 회사 차원은 분모 부재 때문에 품질 순위 용도로 사용하지 않는다.

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
2. 추세: 월별 민원·MoM·YoY 및 taxonomy 경계
3. 운영 검토: product/issue 이상치와 priority 구성요소
4. 역사적 텍스트·품질: 정책 변경 전 TF-IDF 키워드, narrative 존재율, 중복·제외 품질
