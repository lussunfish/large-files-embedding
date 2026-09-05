# TSV 권장 파이프라인

- 배경: 시장품질 TSV는 클레임 원장 덤프이거나 엑셀이 탭으로 내보낸 표다. 구분자만 다를 뿐 CSV와 같다. 최대 ~100MB, 약 3,100건에 섞여 들어온다.
- 관련 문서: `../excel-to-sql-decision.md`, `../xlsx-20-samples-layer1.md`, `README.md`

## 결론

`.tsv`는 Docling CSV 백엔드가 있어도 타지 않는다. **구분자 `\t`를 고정한 06-csv**다. polars `scan_csv(separator='\t')`. 인코딩은 cp949 또는 utf-8-sig. 행을 임베딩하지 않는다. 열이 없으면 txt로 되돌린다. 확장자 `.txt`여도 탭 표면 여기다.

| 선택 | 판단 |
|---|---|
| Docling CSV 백엔드로 TSV 행 임베딩 | 하지 말 것. 백엔드는 있어도 행은 Parquet |
| 각 행을 Milvus 청크로 | 하지 말 것 |
| polars scan_csv(separator='\t') → Parquet | **기본 경로** |
| 클레임 원장 덤프 | SQL 2층 |
| 열이 없는 산문 | txt로 재분류 ([15-txt.md](15-txt.md)) |
| `.txt`인데 탭 헤더면 TSV로 | 여기로 승격 |
| 파일마다 SQL 테이블 | 하지 말 것 |
| 100MB를 pandas로 통째 로드 | 하지 말 것. 스트리밍 |

권장 한 줄:

```
tsv → 시그니처/인코딩(cp949|utf-8-sig) → delimiter=\t → 헤더 행
    → polars scan_csv(separator='\t') → Parquet 1층 → (원장이면) SQL 2층
    → 행 임베딩 금지. 열 없으면 15-txt
```

## 권장 파이프라인

```
업로드 .tsv (또는 탭 표인 .txt/.csv)
  1. 시그니처
       실제로는 xlsx/xml이면 재분류
       탭이 거의 없고 문장만 있으면 15-txt
       쉼표/세미콜론 방언이면 06-csv
  2. 인코딩
       utf-8-sig BOM → utf-8-sig
       한글 깨지면 cp949/euc-kr
       둘 다 실패면 표본 검증 후 실패 큐
  3. 방언
       delimiter 는 `\t` 고정. sniff가 쉼표를 골라도 탭 열이 맞으면 탭
       quoting, 필드 내 개행, 헤더 행 위치
  4. 스트리밍
       polars scan_csv(separator='\t') / pyarrow. 통째 pandas 금지
  5. 프로파일 JSON
       컬럼, 타입, null, 샘플. LLM에는 이것만
  6. Parquet 1층
       source_file, report_period, ingested_at. 원본 컬럼 유지
  7. 분기
       원장/집계 → SQL 2층 + MCP
       원인/대책 긴 칸 → RAG 복제, 테이블 유지
  8. MCP (읽기 전용)
       list_tables, describe_table, query_tables
       벡터에는 카탈로그만
```

## 단계별 권장

### 1. txt와 구분자만 먼저 가른다

TSV는 매직이 약하다. `.txt`로 공유된 원장이 많다. 앞 몇 줄을 보고 탭 열이 안정적인지 본다.

- 헤더 + 탭 + 품번/일자/건수 → **가족 C**. 이 문서
- 탭이 없거나 한 열 문장 → **가족 E**. [15-txt.md](15-txt.md)
- 쉼표/`;`가 본체 → [06-csv.md](06-csv.md)

한국 업무 파일은 `cp949`와 엑셀 `utf-8-sig`가 흔하다. `open(..., encoding="utf-8")` 한 방이 한글을 깨뜨린다.

```python
encoding = detect_cp949_or_utf8sig(path)
# TSV는 sep를 sniff보다 `\t`로 고정하는 편이 안전
# 헤더 표본만 읽고 컬럼 수 변동을 경고한 뒤 scan
```

따옴표 안 탭, 필드 내 개행을 새 행으로 읽으면 컬럼이 밀린다. 헤더가 2~3행이면 xlsx와 같이 이어 붙인다.

### 2. Docling을 건너뛴다

레이아웃이 없다. Docling에 CSV 백엔드가 있어도 행을 임베딩하지 않는다. 100MB에서 표를 다시 추정할 이유가 없다. polars `scan_csv(separator='\t')`가 본체다. 마크다운 파이프 표로 바꿔 청크하지 않는다.

### 3. 원장이면 SQL, 산문이면 txt

- 컬럼이 여러 개이고 품번·건수·일자가 있으면 클레임 원장 → 04와 같은 2층
- 컬럼이 하나이면 서술 메모 → 15-txt. SQL 금지
- 월보성 집계는 스냅샷이다. `source_file`, `report_period` 없이 UNION하지 않는다

1층/2층/MCP는 xlsx·csv와 같다. 파일당 테이블 금지. 실험은 DuckDB, 서비스는 MariaDB. 원인/대책은 삭제하지 않는다. 원본을 채팅에 올리지 않는다.

## 흔한 실패

- `.tsv`를 `.txt`로 임베딩해 숫자가 검색만 되고 집계가 안 됨
- utf-8로 읽어 한글이 `ì`/`?`. 실제는 cp949
- BOM을 컬럼명에 포함 (`\ufeff품번`)
- sniff가 쉼표를 골라 컬럼 1개
- 한 열 산문을 SQL 테이블로 적재
- 행 단위 임베딩으로 “비슷한 클레임” 검색
- 100MB를 `read_csv`로 통째 로드

## 하지 말 것

- TSV를 마크다운 표로 바꿔 Milvus
- Excel에서 다시 저장해 xlsx로 우회 (불필요, 인코딩만 깨짐)
- 확장자 `.txt`라고 15로 고정하는 것
- `pandas.read_csv`로 100MB를 기본 dtype 추론 없이 통째로
- 파일명 = 테이블명 자동 생성
- 원본 TSV 삭제
- `SELECT *`를 Codex에 열어 두기

## 인접 포맷

- `.csv` → [06-csv.md](06-csv.md). 이 문서와 동일, 구분자만 `,`/`;`
- `.txt` → [15-txt.md](15-txt.md). 열 없는 산문을 되돌림
- `.xlsx`/`.xls` → [04-xlsx.md](04-xlsx.md), [05-xls.md](05-xls.md). 시트 내보내기면 같은 패밀리 매핑
- JSON 배열 → [20-json.md](20-json.md). 레코드면 같은 Parquet 경로
- `.xml` 레코드 export → [19-xml.md](19-xml.md) (a) flatten 후 여기와 합류
