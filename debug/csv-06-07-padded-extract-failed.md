# CSV 06/07 ingest — extract_failed

| 항목 | 값 |
|------|-----|
| 파일 | `sample-input/csv/06-govdocs1-472128.csv`, `07-govdocs1-466295.csv` |
| 크기 | 513KB / 547KB. CRLF, 모든 레코드 길이 500자 |
| 일시 | 2026-09-07 |
| 상태 | **solved** — 1층 Parquet 입고, `fact=none` |

## 증상

`uv run python -m large_files_embedding ingest sample-input/csv`

```text
sample-input/csv/06-govdocs1-472128.csv family=C format=csv normalize=false
sample-input/csv/06-govdocs1-472128.csv FAIL reason=extract_failed
sample-input/csv/07-govdocs1-466295.csv family=C format=csv normalize=false
sample-input/csv/07-govdocs1-466295.csv FAIL reason=extract_failed
```

01–05, 08–10은 1층 Parquet 성공 (`fact=none`). 02는 이전 입고 스킵.

로그: `debug/ingest-csv-all.log`

## 조사

둘 다 NIH FY2003 과제 목록(Organization, Grant Number, PI, Title, Award, City, State, Zip). 표가 맞다. 한 열 산문(실패 큐 15)이 아니다.

| 특징 | 값 |
|------|-----|
| 줄 길이 | 전 행 500자 (고정폭 패딩) |
| 1행 | 공백만 |
| 2행 | 따옴표 CSV 헤더. 끝은 `"Zip Code","  "` + 공백 |
| 이후 | 데이터. `ADA TECHNOLOGIES, INC.` 등 필드 안 쉼표 |
| polars 기본 `scan_csv` | 1행을 헤더로 써서 컬럼 1개 → `found more fields than defined in Schema` |

`_csv_skip_rows`는 시장품질 헤더(품번/원인)만 보고 공백 행을 건너뛰지 않는다. `_sniff_delimiter`는 공백 행을 건너뛰어 `,`는 맞다.

우측 공백을 제거하면 python `csv`와 polars `truncate_ragged_lines=True`로 11열 × ~1020행이 나온다.

## 원인

1. 선행 공백 레코드를 헤더로 읽음.
2. 500자 패딩이 따옴표 필드 뒤에 남아 polars가 unescape 실패.
3. `extract()` 예외가 전부 `extract_failed`로 접혀 CLI에 세부 원인이 없음.

## 해결

`calamine_extractor.py`: 샘플이 선행 공백이거나 고정폭 패딩이면 줄을 스트리밍 `rstrip`한 임시 UTF-8을 만들고, `scan_csv(..., truncate_ragged_lines=True)`. 빈 헤더명은 `col_N`.

테스트: `test_fixed_width_padded_csv_extracts_quoted_columns`.

재입고 (`debug/ingest-csv-all-retry.log`):

```text
06-govdocs1-472128.csv sheets=1 profile=a47afad2a27c7735/profile.json parquet=1 fact=none
07-govdocs1-466295.csv sheets=1 profile=8533fdc6bf3e7ff0/profile.json parquet=1 fact=none
```

| 파일 | 행 | 열 |
|------|----|----|
| 06 | 1020 | 11 (Grant Number, PI Name, Award, City, …) |
| 07 | 1088 | 11 (동일 헤더) |

NIH 양식이라 `claim_event` 매핑 없음. 1층만. 마지막 열은 원본의 빈 `"  "` 필드(`col_*` 또는 공백 이름 정리).
