# XLSB 권장 파이프라인

- 배경: 시장품질 RAG/MCP에서 Excel 바이너리 통합문서(`.xlsb`, BIFF12, 가족 C)를 어떻게 넣을 것인가. 대용량 워크북용이다. 약 3,100건, 최대 ~100MB.
- 관련 문서: `../excel-to-sql-decision.md`, `../xlsx-20-samples-layer1.md`, `README.md`

## 결론

`.xlsb`는 OOXML XML이 아니라 **BIFF12 바이너리**다. openpyxl은 읽지 못한다. **polars/fastexcel/calamine이 직접 읽는다.** 병합 셀이 필요하거나 calamine이 실패하면 LibreOffice → xlsx 후 04다. 텍스트 dump는 하지 않는다. 행을 Milvus에 넣지 않는다.

| 선택 | 판단 |
|---|---|
| openpyxl로 `.xlsb` 읽기 | 하지 말 것. OOXML 전용 |
| 셀을 텍스트/마크다운으로 dump 후 임베딩 | 하지 말 것 |
| fastexcel/calamine (polars) 스트리밍 → Parquet | **기본 경로** |
| pyxlsb 스트리밍 | 대안. 값만 |
| LibreOffice → xlsx 후 04 | 폴백. calamine 실패·병합 셀 |
| 파일마다 SQL 테이블 | 하지 말 것 |
| 100MB를 pandas로 통째 로드 | 하지 말 것. 스트리밍 |
| 피벗·차트 시트를 데이터로 | 하지 말 것. 메타만 |

권장 한 줄:

```
.xlsb → 시그니처(BIFF12) → fastexcel/calamine (polars) 스트리밍
      → Parquet 1층 → SQL 2층 (04와 동일). 텍스트 dump·행 임베딩 금지
      → 실패·병합 셀만 LibreOffice → xlsx
```

## 권장 파이프라인

```
업로드 .xlsb
  1. 시그니처
       BIFF12 / Excel Binary Workbook → 이 문서
       ZIP/OOXML                      → 확장자 위조 xlsx/xlsm. 04 또는 21
       OLE(D0 CF)                     → 05-xls
  2. 추출 (기본)
       polars read_excel(engine=calamine) / fastexcel
       xlsb는 lazy load. 병합 셀은 calamine 미지원
       셀 값만. 수식 캐시 값은 숫자로 고정
  3. 폴백
       calamine 실패·병합 셀 필요 시 soffice --headless --convert-to xlsx
       한글 폰트 필수. 원본 보관
  4. 이후는 04-xlsx
       프로파일 JSON → Parquet 1층 → 팩트 SQL 2층
       파일당 테이블 금지. 스냅샷이면 UNION 금지
  5. 메타
       source_format=xlsb, converter=calamine|pyxlsb|libreoffice
  6. MCP
       list_tables / describe_table / query_tables
       벡터에는 카탈로그만. 원인/대책은 RAG 복제, 삭제 금지
```

xlsb는 큰 월보·원장을 작게 주려고 쓰는 경우가 많다. 포맷이 달라도 C 가족 규칙은 같다.

## 단계별 권장

### 1. openpyxl을 시도하지 않는다

`load_workbook('a.xlsb')`는 즉시 실패하거나 빈 워크북이 된다. 입고 로그에 “엑셀 파서 실패”로만 남기면 04와 원인이 섞인다. 시그니처에서 BIFF12를 갈라 calamine(fastexcel)로 보낸다.

calamine은 xlsb를 lazy load한다. 병합 셀은 지원하지 않는다. 병합이 패밀리 규칙이면 LibreOffice 폴백이다. pyxlsb는 행 이터레이터 대안이다. 시트 전체를 DataFrame으로 모으기 전에 타입·널·헤더 표본만 본다. 날짜는 엑셀 시리얼일 수 있다. 04와 같이 변환을 명시한다.

### 2. 대용량이면 스트리밍이 이유다

xlsb를 고른 파일은 100MB xlsx보다 행이 많을 수 있다. pandas `read_excel(engine=...)` 통째 로드를 기본으로 두지 않는다.

```
시트 단위
  → 헤더 후보 5~20행
  → scan/iterate
  → Parquet (source_file, sheet_name, report_period)
```

LibreOffice 폴백은 변환 순간 메모리가 커진다. calamine이 되면 변환을 건너뛴다. 실패·암호·깨진 BIFF12·병합 셀만 soffice로 보낸다. 타임아웃, 워커 하나, CJK 폰트는 [05-xls.md](05-xls.md)와 같다.

### 3. 텍스트로 내보내지 않는다

`ssconvert` 텍스트 모드, `xlsb2csv` 후 마크다운 표, catdoc 계열 dump는 컬럼이 밀리고 한글이 깨진다. CSV가 필요하면 구분자·인코딩을 고정한 뒤 [06-csv.md](06-csv.md)로 보낸다. 그 중간 산출물을 청크하지 않는다.

변환 후 검증은 시트 수·데이터 행 수·한글 깨짐·날짜 시리얼이다. 차트 유실은 허용한다. C 가족은 셀 값이 본체다.

### 4. 이후는 04

원본 컬럼 유지. 유사 양식 20개 프로파일 JSON으로 스키마. 월보 스냅샷과 원장을 섞지 않는다. MCP는 읽기 전용 세 도구, LIMIT 강제. Codex CLI에 `SELECT *`를 열지 않는다.

## 흔한 실패

- openpyxl에 xlsb를 넣어 빈 적재 또는 즉시 실패
- 바이너리를 문자열로 디코드해 청크한다
- 100MB+ 시트를 pandas로 한 번에 올린다
- 변환 성공을 품질 성공으로 본다. 행 수를 안 비교한다
- 위조 xlsx를 xlsb 파서에 넣어 로그가 섞인다
- 파일당 테이블을 만들어 MCP가 헤맨다
- 행 단위 임베딩으로 집계 질의를 대체한다

## 하지 말 것

- `.xlsb`를 텍스트 추출 후 Milvus
- 웹 변환 API에 사내 원장 업로드
- 변환 실패 파일을 빈 Parquet로 적재
- 원본 `.xlsb` 삭제
- 처음부터 3,100개를 RDB에 밀어 넣기
- 매크로가 들어 있으면 실행 (값은 읽고 코드는 끈다)

## 인접 포맷

- `.xlsx` → [04-xlsx.md](04-xlsx.md). 이 문서의 도착점
- `.xls` → [05-xls.md](05-xls.md). 레거시 BIFF8. 같은 calamine 기본
- `.xlsm` → [21-xlsm.md](21-xlsm.md). OOXML+VBA. 값은 04, 매크로 금지
- `.csv`/`.tsv` → [06-csv.md](06-csv.md), [23-tsv.md](23-tsv.md). 이미 텍스트 표
- `.ods` → [24-ods.md](24-ods.md). 다른 컨테이너, 같은 C 가족
