# 데이터 출처와 이용 조건

## CFPB Consumer Complaint Database

- 제공 기관: U.S. Consumer Financial Protection Bureau
- 데이터베이스: https://www.consumerfinance.gov/data-research/consumer-complaints/
- 공개 항목 설명: https://www.consumerfinance.gov/complaint/data-use/
- 이용 조건: CFPB는 공개 데이터가 누구나 사용, 분석, 재활용할 수 있다고 안내합니다. CFPB가 만든 웹사이트 정보는 미국 공공저작물(public domain)로 안내됩니다.

CFPB는 2026-08-14부터 신규 민원 서술문과 자체 시각화의 재량적 공개를 중단한다고 발표했습니다. 이전 공개 서술문은 FOIA 목적의 public domain으로 안내되지만, 이 프로젝트는 공개 동의와 비식별화 절차를 거쳐 과거에 공개된 항목만 역사적 보조 분석에 사용하고 원문을 저장소에 커밋하지 않습니다. 공개 민원은 검증된 위법 사실이나 전체 고객 경험의 대표 표본이 아니므로 회사 품질 순위나 법규 위반 판정에 사용하지 않습니다.

- 정책 변경 공지: https://www.consumerfinance.gov/about-us/newsroom/the-cfpb-to-cease-discretionary-publication-of-complaint-narratives-and-visualizations/

## 실데이터 집계용 고정 미러

공식 API와 bulk 파일 서버가 이 실행 환경에서 HTTP 403을 반환해, 실데이터 집계에는 다음 공개 미러를 사용했습니다.

- 저장소: https://huggingface.co/datasets/Mouwiya/cfpb-consumer-complaints
- 고정 revision: `038f8f8b18879c9384abfee5d0b685b00c03b3cf`
- 미러 설명: CFPB 공개 CSV ZIP을 Parquet로 변환한 자료
- 분석 범위: 2023-09-01~2026-06-30

미러를 공식 CFPB 원본과 동일하다고 단정하지 않습니다. 공식 서버 접근이 복구되면 같은 기간의 행 수와 집계를 다시 대조해야 합니다. 저장소에는 민원 원문을 넣지 않고 상품, 이슈, 응답, 채널, 지역별 집계만 공개합니다. 분석 코드에는 별도 LICENSE의 MIT 조건을 적용합니다.
