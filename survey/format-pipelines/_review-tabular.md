# 정형 파이프라인 리뷰 (2026-09)

대상: `04-xlsx`, `05-xls`, `06-csv`, `19-xml`, `20-json`, `21-xlsm`, `22-xlsb`, `23-tsv`, `24-ods`, `39-yaml`, `40-parquet`.
패치는 제자리. 하다/다 체 유지. 전면 재작성 없음.

## 사실 (2026-09)

- Polars `read_excel` 기본 엔진은 calamine(fastexcel / Rust calamine). `.xlsx` `.xlsb` `.xls` 지원. openpyxl보다 훨씬 빠르다.
- python-calamine / calamine crate: xls, xlsx, xlsm, xlsb, xla/xlam, ods. xlsb는 lazy load. 병합 셀은 미지원.
- pandas 3.1 `engine='calamine'`은 xls/xlsx/xlsm/xlsb/ods. xlsx/xlsm 기본 엔진은 openpyxl → calamine으로 옮길 예정.
- Docling XLSX 백엔드는 openpyxl. XLS는 LibreOffice 변환. 시트 차트를 TableData로 뽑을 수 있다. 100MB SQL 경로에 쓰지 않는다.
- Docling ODS는 `OdsDocumentBackend`(odfdo). 시트를 문서로 볼 때. 가족 C(SQL)는 calamine/polars.
- Docling CSV 백엔드는 있다. 행 임베딩은 금지. parquet/`scan_csv` 유지.
- Docling 범용 XML/JSON/YAML 백엔드는 없다. USPTO/JATS/XBRL/DocLang만.

## 잘못된 기본 경로 (패치 전)

LibreOffice가 1순위였던 곳:

| 파일 | 패치 전 | 패치 후 |
|---|---|---|
| 05-xls | LibreOffice → xlsx가 **기본** | calamine 직접 읽기. LO는 이상한 BIFF·차트 |
| 22-xlsb | pyxlsb 또는 LibreOffice | fastexcel/calamine 기본. LO는 실패·병합 셀 |
| 24-ods | LO → xlsx가 운영 기본 | calamine/polars 기본. LO는 폴백. Docling ODS는 문서 경로 |

## 파일별

### 04-xlsx.md

이미 calamine/polars가 기본이었다. fastexcel을 기본 엔진으로 명시했다. openpyxl은 차트·정의된 이름·병합 셀 수리만. Docling XLSX(openpyxl)를 SQL 경로에서 금지. `.xls` 인접 링크를 LibreOffice-first에서 calamine 직접으로 고쳤다.

### 05-xls.md

가장 큰 수정. “직접 파싱하지 않는다 / LO가 기본”을 폐기. 선택 표·권장 한 줄·파이프라인 2단계를 calamine 우선으로 바꿨다. xlrd 1.2/2.x·openpyxl 금지는 유지. “calamine이 읽는데도 LO로 보낸다”를 흔한 실패에 넣었다.

### 21-xlsm.md

calamine이 **값만** 읽고 VBA는 무시한다는 문장을 고정. VBA 실행 금지는 유지. fastexcel을 기본 추출로 표기. LO는 값 추출 실패 폴백(매크로 제거).

### 22-xlsb.md

1순위를 pyxlsb/LO에서 polars/fastexcel/calamine으로. xlsb lazy load, 병합 셀 미지원을 적었다. pyxlsb는 대안. LO는 실패·병합 셀.

### 24-ods.md

LO/odfpy/Docling excel을 1순위에서 내렸다. 가족 C는 calamine/polars scan. Docling odfdo는 시트-as-문서. odfpy는 보조.

### 06-csv.md / 23-tsv.md

Docling CSV 백엔드가 있어도 행을 임베딩하지 않는다. 기본은 `polars scan_csv` → Parquet. 구분·인코딩·원장 SQL은 유지.

### 40-parquet.md

DuckDB/polars `scan_parquet`가 맞다. 선택 표와 권장 한 줄만 `scan_parquet`로 맞춰 두었다. 재임베딩·CSV 왕복 금지는 그대로.

### 19-xml.md / 20-json.md / 39-yaml.md

이중 분기(정형 flatten vs 문서 경로) 유지. Docling 범용 XML/JSON/YAML이 없음을 선택 표·한 줄·하지 말 것에 넣었다. XML은 USPTO/JATS/XBRL/DocLang만 예외.

## README.md (이번 목록 밖, 불일치)

패치하지 않았다. 표와 입고 분기가 아직 LO-first다.

- 공통 원칙 4: 레거시 `.xls`를 LibreOffice 정규화로 묶음. `.doc`/`.ppt`는 맞다. `.xls`는 아님.
- 목록 5 XLS: “LibreOffice → XLSX 후 04”.
- 목록 22 XLSB: “pyxlsb 또는 LibreOffice”.
- 입고 분기: `xls/xlsb/ods/cell → 변환 후 C`. cell만 변환이 맞다.

## 유지한 규칙

- 가족 C는 행 임베딩 금지. Parquet 1층 → SQL 2층.
- 매크로/VBA 미실행. `vbaProject.bin` 미인덱싱.
- 100MB 통째 로드 금지. openpyxl `load_workbook` 금지.
- 파일당 테이블 금지. 월보 스냅샷 UNION 금지.
- MCP는 `list_tables` / `describe_table` / `query_tables` 읽기 전용.
- 원인/대책 칸은 SQL에서 삭제하지 않고 RAG로만 복제.
