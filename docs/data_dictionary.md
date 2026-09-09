# KPI와 데이터 사전

| 항목 | 정의 | 주의점 |
|---|---|---|
| complaints | 완료 월에 수신된 중복 제거 Complaint ID 수 | 최신 2개 불완전 월 제외 |
| MoM / YoY | 전월 / 전년동월 대비 `(현재-비교)/비교` | 비교 월이 0이면 NULL |
| timely_response_rate_pct | `Timely response?`가 Yes/No인 행에서 Yes 비율 | 공백/Unknown은 분모 제외 |
| avg_days_to_company | 발송일~회사응답일 차이 평균 | 둘 중 하나가 없으면 제외 |
| relief shares | 회사 응답 중 monetary/non-monetary relief 비율 | 결과와 보상 사실의 인과로 해석 금지 |
| product/issue concentration | product와 issue별 민원 건수 비중 | 분류체계 버전과 함께 비교 |
| channel/state mix | Submitted via와 State 분포 | 신고 채널 접근성 편향 가능 |
| narrative availability | 역사적 공개 서술문 존재 비율 | 비공개/미제출 및 2026-08-14 정책 변경 이후 신규 건은 텍스트 추세 분석 대상 아님 |
| anomaly_count | 최소 건수와 rolling robust z 기준 통과 product/issue/month 수 | 탐지 결과는 조사 우선순위 신호 |
| priority_score | volume, growth, untimely, relief, persistence 정규화 가중합 | 기본 가중치 합계는 1 |

원천 필드는 CFPB 공식 헤더를 snake_case로 바꾼다. `taxonomy_version`은 CFPB가 안내한 2023년 8월 변경 월을 기준으로 `pre_2023_08_update`와 `post_2023_08_update`를 보존한다. 일 단위 공식 전환일을 주장하지 않으며 실제 추세 분석 범위는 2023년 9월 이후다.
