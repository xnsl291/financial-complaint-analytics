# CFPB 실데이터 집계 결과

## 분석 범위

- 기간: 2023-09-01~2026-06-30
- 완전 월: 34개월
- 민원 수: 12,344,954건
- 수집 경로: CFPB bulk export의 고정 Parquet 미러
- 원문 저장: 없음

## 주요 관찰

신용보고 또는 기타 개인 소비자 보고 상품은 10,895,477건으로 전체의 88.26%였다. 이 상품군을 분리하지 않으면 전체 추세가 다른 상품의 변화를 가린다.

2026년 6월 `Incorrect information on your report`는 417,406건으로 전년 동월보다 102.35% 늘었다. `Problem with a company's investigation into an existing problem`도 133,979건으로 112.85% 증가했다.

같은 달 채권추심의 `Took or threatened to take negative or legal action`은 11,146건으로 전년 동월보다 399.15% 늘었다. 예금계좌의 `Managing an account`는 4,971건으로 60.41%, 신용카드의 `Problem with a purchase shown on your statement`는 2,773건으로 74.84% 증가했다.

전체 적시응답률은 99.59%였지만 Student loan 상품은 79.13%였다. 이 차이는 회사 품질 순위가 아니라 해당 상품의 데이터 정의, 처리 경로, 시기별 구성 변화를 먼저 확인해야 할 신호다.

## 해석 경계

민원 수는 고객 수나 시장점유율로 보정하지 않았다. 회사별 민원 수로 품질 순위를 만들지 않으며, 급증 신호도 규제 위반이나 원인을 뜻하지 않는다. 미러 변환본의 행 수와 집계는 공식 서버 접근이 복구되면 다시 대조해야 한다.
