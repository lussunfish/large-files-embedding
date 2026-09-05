# CSV 권장 파이프라인

- 배경: 시장품질 CSV는 클레임 원장 덤프이거나 한 열짜리 서술이다. 전자는 SQL, 후자는 txt다. 최대 ~100MB, 약 3,100건 코퍼스에 섞여 들어온다.
- 관련 문서: `../excel-to-sql-decision.md`, `../xlsx-20-samples-layer1.md`, `README.md`

## 결론

CSV는 Docling CSV 백엔드가 있어도 타지 않는다. 인코딩·구분자·헤더만 잡고 polars `scan_csv`로 Parquet 1층에 간다. 행을 임베딩하지 않는다. 클레임 원장 덤프면 SQL 2층이다. 한 열 산문이면 txt로 재분류한다.

| 선택 | 판단 |
|---|---|
| Docling CSV 백엔드로 행 임베딩 | 하지 말 것. 백엔드는 있어도 행은 Parquet |
| 각 행을 Milvus 청크로 | 하지 말 것 |
| polars scan_csv → Parquet 1층 | **기본 경로** |
| 클레임 원장 덤프 | SQL 2층 |
| 한 열짜리 서술 | txt로 재분류 (15) |
| 파일마다 SQL 테이블 | 하지 말 것 |
| 100MB를 pandas로 통째 로드 | 하지 말 것. 스트리밍 |

권장 한 줄:

```
csv → 시그니처/인코딩(cp949|utf-8-sig) → 구분자(, ; \t) → 헤더 행
    → polars scan_csv → Parquet 1층 → (원장이면) SQL 2층. 행 임베딩 금지
```

## 권장 파이프라인

```
업로드 .csv
  1. 시그니처
       실제로는 xlsx/xml이면 재분류
       한 열·개행 문장만 있으면 15-txt
  2. 인코딩
       utf-8-sig BOM → utf-8-sig
       한글 깨지면 cp949/euc-kr 시도
       둘 다 실패면 표본 검증 후 실패 큐
  3. 방언
       delimiter `,` `;` `\t`
       quoting, escape, 헤더 행 위치
  4. 스트리밍 읽기
       polars scan_csv / pyarrow. 통째로 pandas 로드 금지
  5. 프로파일 JSON
       컬럼, 타입, null, 샘플. LLM에는 이것만
  6. Parquet 1층
       source_file, report_period, ingested_at
       원본 컬럼 유지
  7. 분기
       원장/집계 → SQL 2층 + MCP
       원인/대책 긴 칸 → RAG 복제, 테이블 유지
  8. MCP (읽기 전용)
       list_tables, describe_table, query_tables
       벡터에는 카탈로그만
```

## 단계별 권장

### 1. 방언을 먼저 고정한다

한국 업무 CSV는 `cp949` + 쉼표, 또는 엑셀 저장본 `utf-8-sig`가 많다. 유럽형 `;`와 TSV `\t`도 섞인다.

```python
encoding = detect_cp949_or_utf8sig(path)
sep = sniff_delimiter(path, encoding)  # , ; \t
# 헤더 표본만 읽고 방언을 확정한 뒤 scan_csv
```

따옴표 안 쉼표, 필드 내 개행, `#` 주석 행을 무시하면 컬럼이 밀린다. 프로파일러가 행마다 컬럼 수 변동을 경고해야 한다. 헤더가 2~3행이면 xlsx와 같이 이어 붙인다.

### 2. Docling을 건너뛴다

CSV는 레이아웃이 없다. Docling에 CSV 백엔드가 있어도 행을 임베딩하지 않는다. 100MB에서 표를 다시 추정할 이유가 없다. polars `scan_csv`가 본체다. 마크다운 표로 바꿔 청크하지 않는다.

### 3. 원장이면 SQL, 산문이면 txt

- 컬럼이 여러 개이고 품번·건수·일자가 있으면 **클레임 원장 덤프** → 04와 같은 2층
- 컬럼이 하나이고 문장이 이어지면 **서술 메모** → 15-txt. SQL 금지
- 구분자가 거의 없고 HTML/XML이면 재분류한다
- 월보성 집계 CSV는 스냅샷이다. `source_file`, `report_period` 없이 UNION하지 않는다

### 4. 1층/2층/MCP는 xlsx와 같다

파일당 테이블 금지. 스트리밍. 원본 컬럼 유지. 실험은 DuckDB, 서비스는 MariaDB. MCP는 `list_tables` / `describe_table` / `query_tables` 읽기 전용. 벡터는 카탈로그만. 원인/대책은 삭제하지 않는다.

100MB CSV도 워크북과 같다. `scan_csv`로 스트리밍하고 전체 `read_csv` 메모리 로드를 피한다. 유사 파일 20개의 프로파일 JSON으로 스키마를 맞춘다. 원본을 채팅에 올리지 않는다.

## 흔한 실패

- utf-8로 읽어 한글이 `ì`/`?`. 실제는 cp949
- BOM을 컬럼명에 포함 (`\ufeff품번`)
- `;` 파일을 쉼표로 읽어 컬럼 1개
- 헤더가 3행인데 1행을 컬럼으로 사용
- 한 열 산문을 SQL 테이블로 적재
- 행 단위 임베딩으로 “비슷한 클레임” 검색. 집계가 틀림
- 따옴표 안 개행을 새 행으로 읽어 컬럼이 밀림

## 하지 말 것

- CSV를 마크다운 표로 바꿔 Milvus
- Excel에서 다시 저장해 xlsx로 우회 (불필요, 인코딩만 깨짐)
- `pandas.read_csv`로 100MB를 기본 dtype 추론 없이 통째로
- 파일명 = 테이블명 자동 생성
- 원본 CSV 삭제
- `SELECT *`를 Codex에 열어 두기

## 인접 포맷

- `.xlsx`/`.xls` → 04/05. CSV가 시트 내보내기면 같은 패밀리 매핑을 재사용
- `.tsv` → 구분자만 `\t`. 이 문서와 동일
- JSON 배열 → 20. 레코드면 같은 Parquet 경로
- `.txt` → 15. 여기로 잘못 들어온 산문을 되돌림
- `.xml` 레코드 export → 19 (a) flatten 후 여기와 합류
