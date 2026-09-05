# JSON 권장 파이프라인

- 배경: 시장품질 JSON은 API 덤프(레코드 배열)와 중첩 보고서 블롭이 섞인다. JSON 원문을 한 청크로 넣지 않는다. 100MB는 스트리밍이다.
- 관련 문서: `../excel-to-sql-decision.md`, `../xlsx-20-samples-layer1.md`, `README.md`

## 결론

배열/레코드면 데이터프레임 → Parquet/SQL, 중첩 문서면 경로를 살린 추출이다. JSONL은 줄 단위다. Docling 범용 JSON 백엔드는 없다. 스키마는 jq/python이 추론하고, LLM에는 프로필만 준다.

| 선택 | 판단 |
|---|---|
| JSON 파일 전체를 한 청크로 임베딩 | 하지 말 것 |
| 레코드 배열 → DataFrame/SQL | **정형 분기 (a)** |
| 중첩 문서/API 블롭 → 경로 유지 추출 | **문서 분기 (b)** |
| JSONL을 통째로 json.load | 하지 말 것. 줄 단위 |
| 100MB를 메모리에 로드 | 하지 말 것. ijson/스트리밍 |
| Docling 범용 JSON 백엔드 | 없음. 이중 분기 유지 |
| 파일마다 SQL 테이블 | 하지 말 것 |

권장 한 줄:

```
json → 스키마 추론(jq/python) → (a) 배열이면 DataFrame → Parquet → SQL
                                → (b) 중첩 문서면 path 유지 텍스트/typed extract
     JSONL은 줄 단위. 원문 통째 임베딩 금지. 100MB는 ijson. Docling 범용 JSON 없음
```

## 권장 파이프라인

```
업로드 .json / .jsonl
  1. 시그니처
       JSONL(줄마다 객체) / 배열 / 단일 객체 / 위조 확장자
  2. 스트리밍 프로파일
       ijson 또는 줄 단위. 키 경로, 타입, 배열 길이
       LLM에는 스키마 JSON만 (원문 100MB 금지)
  3a. 레코드 배열
       최상위 [] 또는 $.data[] / $.items[]
       json_normalize → Parquet 1층(원본 키 유지) → SQL 2층
  3b. 중첩 문서
       경로를 키로 남김 ($.report.cause)
       긴 문자열 필드만 RAG, 숫자는 typed extract
  4. MCP
       정형: list_tables / describe_table / query_tables (읽기 전용)
       문서: outline / section / search
  5. 벡터
       카탈로그 또는 서술 필드만. JSON 원문 통째 금지
       원인/대책은 RAG 복제, 테이블에서 삭제하지 않음
```

## 단계별 권장

### 1. 스키마를 코드가 추론한다

jq/python으로 키 경로와 카디널리티를 센다. 모델은 프로필만 본다. xlsx 20개 표본과 같은 프로토콜이다.

```
.[] | keys
paths(scalars) | map(tostring) | unique
```

유사 파일 20개면 스키마 정렬이 된다. 원문 100MB를 채팅에 올리지 않는다.

### 2. 정형 분기 (a)

- 최상위가 객체 배열, 또는 한 단계 아래 `items`/`records`/`data`
- 키가 컬럼, 값이 스칼라 위주
- `pandas.json_normalize` / polars. 1층은 원본 키 유지
- 파일당 테이블 금지. `source_file`, `report_period`, `ingested_at`
- 월보성 덤프는 스냅샷이다. UNION하지 않는다
- 이후 04와 동일. 숫자는 SQL, MCP는 읽기 전용 세 도구

### 3. 문서 분기 (b)

- 키가 섹션이고 값이 긴 문자열·혼합 객체
- 경로를 breadcrumb로 붙인다: `report > 원인 > 대책`
- 숫자 필드는 typed extract로 SQL 후보에 따로 둔다
- 원문 JSON을 청크 본문에 넣지 않는다
- 표형 배열이 안에 있으면 그 경로만 (a)로 승격한다

### 4. JSONL과 100MB

- JSONL: 한 줄 = 한 레코드. 줄마다 `json.loads`. 파일 전체 `json.load` 금지
- 100MB 단일 JSON: `ijson`으로 배열 원소 단위. `json.load`는 OOM이다
- NDJSON 클레임 덤프는 (a)로 바로 Parquet
- 깨진 줄은 실패 큐. 전체를 버리지 않는다

### 5. 하이브리드 필드

원인/대책이 JSON 문자열이어도 테이블에서 지우지 않는다. RAG로 복제만 한다. 벡터에는 카탈로그 + 그 서술 필드다. 행 데이터 전체를 임베딩하지 않는다.

## 흔한 실패

- 100MB `json.load` OOM
- JSONL을 표준 JSON으로 파싱해 첫 줄에서 실패
- 파일 전체를 코드펜스 청크로 임베딩
- 중첩 배열을 `str(dict)`로 한 컬럼에 넣고 집계
- API 래퍼 `{status, data:[...]}`를 문서로 오분류
- 스키마가 파일마다 다른데 테이블을 파일명으로 양산
- 원인/대책 키를 2층에서 drop

## 하지 말 것

- JSON을 Docling/마크다운으로 우회 (범용 JSON 백엔드 없음)
- 원문 전체를 Milvus에 1청크
- 외부 URL을 따라가는 JSON 레퍼런스 자동 fetch (SSRF)
- 파일당 SQL 테이블
- 2층에서 서술 키를 drop
- `SELECT *`를 Codex에 열어 두기
- 100MB JSON을 LLM 채팅에 업로드

## 인접 포맷

- `.xml` 레코드 → 19 (a)와 같은 flatten
- `.csv` → 이미 평탄. 06
- `.xlsx` → 04. JSON이 엑셀 내보내기면 매핑 재사용
- `.txt`/`.md` → JSON이 아닌 산문이 `.json`으로 온 경우 재분류
- `.jsonl`/NDJSON → 이 문서의 줄 단위 경로. 별도 파이프라인 없음
