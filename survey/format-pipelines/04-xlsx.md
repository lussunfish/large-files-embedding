# XLSX 권장 파이프라인

- 배경: 시장품질 문서 약 3,100건 중 xlsx 비중이 높고, 단일 파일이 최대 ~100MB다. 숫자는 SQL, 서술은 RAG다.
- 관련 문서: `../excel-to-sql-decision.md`, `../xlsx-20-samples-layer1.md`, `README.md`

## 결론

xlsx는 벡터에 넣지 않는다. 스트리밍으로 뽑고, Parquet 1층에 원본 컬럼을 남긴 뒤, 공통 팩트만 MariaDB/DuckDB 2층에 올린다. 유사 양식 20개는 원본 업로드가 아니라 프로파일 JSON으로 스키마를 맞춘다.

| 선택 | 판단 |
|---|---|
| xlsx를 Milvus 텍스트 청크로 넣기 | 하지 말 것 |
| 파일마다 SQL 테이블 1개 | 하지 말 것 |
| openpyxl로 100MB 워크북 전체 로드 | 하지 말 것 |
| fastexcel/calamine (polars 기본 엔진) → Parquet 1층 | **기본 경로** |
| openpyxl | 차트·정의된 이름·병합 셀 수리만 |
| Docling XLSX 백엔드로 SQL 경로 | 하지 말 것. 내부는 openpyxl |
| 공통 팩트만 curated SQL 2층 | 해야 함 |
| 유사 양식 20개 → 프로파일 JSON → LLM 스키마 정렬 | 1층 설계의 본업 |
| 피벗·차트·매크로 시트를 데이터로 적재 | 하지 말 것. 메타만 |

권장 한 줄:

```
xlsx → 시그니처 → fastexcel/calamine (polars 기본) 스트리밍 → Parquet 1층(원본 컬럼 유지)
     → 표준 팩트 SQL 2층 → MCP list_tables / describe_table / query_tables
     → 벡터에는 카탈로그만. 원인/대책은 RAG 복제, 테이블에서 삭제하지 않음
```

## 권장 파이프라인

```
업로드 .xlsx (~100MB)
  1. 시그니처
       ZIP/OOXML 아니면 .xls 게이트 또는 재분류
  2. 시트 인벤토리
       차트/피벗/매크로/빈 시트 건너뜀. 메타만 남김
  3. 스트리밍 추출
       polars read_excel(engine=calamine) / fastexcel
       openpyxl은 차트·정의된 이름·병합 셀 수리만. 전체 로드 금지
  4. 프로파일러 JSON (파일당 2~10KB)
       시트명, 행/열, 헤더 후보, 타입, null, 샘플 5행
  5. 유사 양식 20개 → LLM 스키마 정렬
       100MB 원본을 채팅에 올리지 않음. mapping.yml 산출
  6. 1층 Parquet
       source_file, sheet_name, report_period, template_family
       원본 컬럼 유지
  7. 스냅샷 vs 원장
       월보면 UNION 금지. source_file + report_period + ingested_at
  8. 2층 SQL
       claims, monthly_quality_kpi 등 최소 팩트. DuckDB 검증 후 MariaDB
  9. MCP (읽기 전용)
       list_tables, describe_table, query_tables. LIMIT 강제
 10. 벡터
       테이블/컬럼 설명만. 행 데이터 금지
       원인/대책 긴 칸은 RAG 복제, SQL에서 삭제하지 않음
```

## 단계별 권장

### 1. 파싱은 스트리밍만

100MB xlsx는 압축 XML이다. 풀면 수백만 행·메모리 폭주가 난다.

- Polars `read_excel` 기본 엔진은 calamine(fastexcel). python-calamine과 같다. openpyxl보다 훨씬 빠르다
- `.xlsx`/`.xlsm`/`.xlsb`/`.xls`를 시트 단위로 읽는다
- 워크북 전체를 메모리에 올리지 말 것
- openpyxl은 차트·정의된 이름·병합 셀 수리에만 쓴다. `load_workbook` 전체 로드 금지
- Docling XLSX 백엔드는 openpyxl이다. 시트 차트를 TableData로 뽑을 수는 있다. 100MB SQL 경로에는 쓰지 않는다
- 날짜는 엑셀 시리얼 숫자다. 변환을 명시한다
- 병합 셀은 1층에서 값 전파 여부를 패밀리 규칙으로 고정한다. 수리가 필요하면 그때만 openpyxl

### 2. 20개 표본으로 스키마를 맞춘다

3,100개를 모델이 읽지 않는다. 같은 템플릿 20개가 1층 추출기다.

```
20개 xlsx
  → (코드) 프로파일러 JSON
  → (LLM) 패밀리 분류 + 표준 스키마 + mapping.yml
  → (코드) Parquet 랜딩
  → 실패 파일만 다시 봄
```

같은 월보 템플릿이면 매핑 한 번으로 이후 파일은 스크립트가 처리한다. 양식이 3~5종이면 패밀리별 매퍼가 필요하다. 100MB를 채팅에 올리는 방식은 기각한다.

### 3. 1층은 버리지 않는다

파일/시트당 Parquet 하나. 정규화는 2층이다.

- 원본 컬럼 유지. 헤더 두 행이면 `col_클레임_건수`처럼 이어 붙인다
- 완전히 빈 시트, 차트시트, 피벗, 매크로 시트만 제외
- 원인/대책 긴 칸은 삭제하지 않는다. 나중에 RAG로 복제한다

### 4. 스냅샷과 원장을 섞지 않는다

- **원장**: 한 행 = 클레임 1건. UNION이 맞다
- **월보 스냅샷**: 같은 집계가 매월 파일로 쌓인다. UNION하면 중복 집계다
- 공통 메타: `source_file`, `sheet_name`, `report_period`, `ingested_at`, `template_family`

### 5. 2층은 파일 테이블이 아니다

파일마다 테이블을 만들면 Codex가 어떤 표를 칠지 모른다. 최소 팩트 2~3개만 설계한다. 예: `claim_event`, `monthly_quality_kpi`. 실험은 DuckDB + Parquet, 서비스는 MariaDB/Postgres다.

### 6. MCP와 벡터

- `list_tables(product, period)` — 어떤 표가 있는지
- `describe_table(name)` — 컬럼 의미, 단위, Grain(한 행이 무엇인지)
- `query_tables(sql)` — 읽기 전용, 허용 스키마만, LIMIT 강제
- 벡터: “`claims` 한 행 = 클레임 1건 …” 카탈로그만
- 원인/대책은 텍스트로 복제해 RAG한다. 테이블 컬럼은 유지한다

## 흔한 실패

- openpyxl로 100MB를 통째로 로드해 OOM
- 피벗/차트 시트를 데이터로 적재
- 월보 스냅샷을 UNION 해 건수가 3배가 됨
- 헤더 위 제목 행을 컬럼명으로 읽음
- 파일당 테이블 3,100개 → MCP가 헤맴
- 원인/대책을 SQL에서 지우고 RAG만 남김. 재처리가 안 됨
- 100MB 원본을 LLM 채팅에 올려 일부만 보고 스키마를 확정

## 하지 말 것

- xlsx를 Docling → 마크다운 → Milvus
- Docling XLSX 백엔드로 100MB를 SQL 적재
- 100MB 원본을 LLM 채팅에 업로드
- xlsx를 MariaDB BLOB로 보관
- 처음부터 3,100개를 RDB에 밀어 넣기
- `SELECT *`를 Codex에 열어 두기
- 1층에서 “의미 없는 컬럼”을 임의로 drop

## 인접 포맷

- `.xls` → [05-xls.md](05-xls.md). calamine이 직접 읽는다. 이상한 BIFF만 LibreOffice
- `.csv` → 인코딩만 잡고 바로 Parquet ([06-csv.md](06-csv.md)). Docling 불필요
- 표형 XML/JSON → 같은 C 가족, 스트리밍 flatten ([19-xml.md](19-xml.md), [20-json.md](20-json.md))
- Word 안의 작은 표는 [02-docx.md](02-docx.md). 같은 양식이 반복되면 여기로 승격
