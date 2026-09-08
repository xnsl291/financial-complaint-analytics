# 금융민원 이상징후 분석

CFPB Consumer Complaint Database를 2023-09 이후 기준으로 분석하는 재현 가능한 포트폴리오 프로젝트입니다. 추세 판단에서는 실행일 기준 최근 2개 불완전 월을 동적으로 제외합니다. 회사별 고객 수·시장점유율 분모가 없으므로 **회사 품질 순위나 상대적 우열을 주장하지 않습니다.**

## 실행

Python 3.12에서 프로젝트 로컬 환경을 만든 뒤 다음처럼 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m src.pipeline all --demo
```

실데이터는 공식 CFPB API를 제한 행 수로 요청합니다. 원본 응답은 `data/raw/`에 보존되며 Git에서 제외됩니다.

```powershell
.\.venv\Scripts\python.exe -m src.pipeline ingest --row-cap 200 --snapshot-date 2026-09-08
.\.venv\Scripts\python.exe -m src.pipeline all --row-cap 200 --snapshot-date 2026-09-08
```

명령은 `ingest`, `validate`, `transform`, `analyze`, `export-bi`, `verify`, `all`을 제공하며, 현재 독립 단계 검토에는 `--demo`를 사용합니다. `all --demo`는 전체 계층을 다시 생성합니다.

## 산출물

- `data/raw`: 보존 원본(무시됨), `data/staging`: 표준화 결과, `data/mart/complaints.duckdb`: DuckDB 스타/분석 마트
- `bi`: Power BI용 CSV, 스키마, 테마
- `reports/power_bi_preview_page_1.png`~`4.png`, `reports/power_bi_preview.pdf`: 실제 파이프라인 출력 기반 4페이지 정적 미리보기
- `docs`: 지표 정의, BI 모델, 한계, 면접 문답과 지원용 요약

## 분석 원칙

Complaint ID는 첫 관측값만 유지하고, 날짜 오류·빈 범주를 표준화합니다. CFPB가 안내한 2023년 8월 분류체계 변경 월을 `pre_2023_08_update`와 `post_2023_08_update`로 보존해 명칭 변경을 단일 추세처럼 오인하지 않게 합니다. 실제 분석 범위는 2023년 9월 이후입니다. 이상치는 최소 건수와 3개월 rolling baseline의 robust z-score를 함께 사용하고, 이후 월에도 높은 수준이 이어지면 persistent, 아니면 spike로 표시합니다. CFPB가 2026-08-14부터 신규 민원 서술문 공개를 중단했으므로 텍스트 분석은 이전에 공개된 역사 자료에만 적용하는 보조 분석입니다. 영어 불용어 제거 후 TF-IDF/1~2-gram만 사용하며 LLM·자동 컴플라이언스 판정은 하지 않습니다.

자세한 정의와 Power BI 구성은 [docs/data_dictionary.md](docs/data_dictionary.md), [docs/power-bi-guide.md](docs/power-bi-guide.md)를 보세요.

분석 방법, 데모 검증 결과와 실데이터 적용 한계는 [docs/analysis_report_ko.md](docs/analysis_report_ko.md)에 정리했습니다.

데이터 출처·공개 데이터 해석 원칙은 [`DATA_SOURCES.md`](DATA_SOURCES.md), 분석 코드 라이선스는 [`LICENSE`](LICENSE)를 확인하세요.
