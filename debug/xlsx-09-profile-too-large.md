# XLSX 09 ingest — profile_too_large

| 항목 | 값 |
|------|-----|
| 파일 | `sample-input/xlsx/09-3_1_Generator_Y2022.xlsx` |
| 크기 | 9.97MB. EIA 발전기 명부 3시트 |
| 일시 | 2026-09-07 |
| 상태 | **solved** — 프로필 JSON만 축소. 1층 Parquet 3시트, `fact=none` |

## 증상

`uv run python -m large_files_embedding ingest sample-input/xlsx`

```text
09-3_1_Generator_Y2022.xlsx family=C format=xlsx normalize=false
09-3_1_Generator_Y2022.xlsx FAIL reason=profile_too_large
```

01–08, 10은 1층 Parquet 성공 (`fact=none`). 로그: `debug/ingest-xlsx-all.log`

## 조사

추출 자체는 된다. fastexcel이 시트 3개를 읽는다.

| 시트 | 행 | 열 |
|------|----|----|
| Operable | 25380 | 73 |
| Proposed | 2025 | 47 |
| Retired and Canceled | 4945 | 57 |

`TabularProfile.to_json_bytes`는 샘플을 5행→1행→0행으로 줄이지만, `header_candidates` / `types` / `nulls` / `original_columns`는 전 열을 세 번 넣는다. 최축도 **15357바이트** > `PROFILE_JSON_MAX_BYTES`(10KB). `validate_extracted_tabular`가 그 시점에 실패해서 Parquet/MinIO까지 가지 않는다.

## 원인

PLAN은 프로필을 2–10KB 지문으로 두라고 한다. 넓은 시트를 **입고 실패**로 취급하는 게 아니라, JSON만 잘라야 한다. 1층 원본 컬럼은 Parquet에 그대로 둔다.

## 해결

`to_json_bytes`가 샘플 축소 후에도 크면 열 목록을 20개, 그다음 8개로 cap. `n_rows`/`n_cols`는 실제 값. 단위 테스트 `test_wide_workbook_profile_json_is_clipped_under_limit`.

재입고 (`debug/ingest-xlsx-09-retry.log`):

```text
09-3_1_Generator_Y2022.xlsx sheets=3 profile=1130fd4ce3a1d49f/profile.json parquet=3 fact=none
```
