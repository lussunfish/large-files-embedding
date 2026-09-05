# Parquet 권장 파이프라인

- 배경: 이 프로젝트의 정형 1층 랜딩이 Parquet다. 시장품질 xlsx/csv/한셀이 여기로 모인다. 이미 컬럼형인 파일을 다시 문서처럼 청크하지 않는다.
- 관련 문서: `README.md`, `../excel-to-sql-decision.md`, `../xlsx-20-samples-layer1.md`, [04-xlsx.md](04-xlsx.md)

## 결론

`.parquet`는 가족 C다. **이미 컬럼형 저장소다.** DuckDB/polars로 스캔한다. 행을 임베딩하지 않는다. 이 파일이 1층 랜딩이면 변환 없이 `query_tables`로 바로 조회한다. 스키마·Hive 파티션·압축을 입고에서 검증한다. 문서 블롭이 중첩돼 있어도 SQL/스캔이지 RAG가 아니다. CSV로 풀었다가 다시 만들지 않는다.

권장 한 줄:

```
.parquet → 시그니처(PAR1) → 스키마/파티션/압축 검증
        → DuckDB·polars scan_parquet (통째 메모리 로드 금지)
        → 이미 1층이면 재추출 없이 MCP query_tables
        → 벡터에는 카탈로그만. 행 임베딩 금지
        csv 왕복 금지
```

| 선택 | 판단 |
|---|---|
| Parquet 행을 Milvus 청크로 | 하지 말 것 |
| 1층 랜딩인데 다시 xlsx/csv로 변환 | 하지 말 것 |
| DuckDB/polars scan_parquet + SQL | **기본 경로** |
| 스키마·Hive 파티션·압축 검증 | 해야 함 |
| 중첩 struct를 문서로 RAG | 하지 말 것. 그래도 스캔 |
| pandas로 100MB+ 통째 load | 하지 말 것 |
| Docling | 해당 없음 |

## 권장 파이프라인

```
업로드 .parquet 또는 hive 디렉터리
  1. 시그니처
       PAR1 매직. 확장자만 믿지 말 것
       CSV/JSON/ZIP 위조면 재분류 (06 / 20 / 컨테이너)
  2. 풋터·메타 점검
       스키마, row group 수, 행 수, 압축(codec)
       Hive 파티션 키 (product=, period=, ... )
       깨진 풋터·암호화·0바이트는 failed_parquet
  3. 역할 판별
       이 프로젝트 1층 랜딩     → 재추출 없이 카탈로그 등록
       외부 덤프/첨부 parquet    → 프로파일 JSON 후 같은 1층에 편입
       중첩 struct/list of 문서  → 그래도 SQL/scan. 텍스트 칸만 선택 복제
  4. 조회
       DuckDB scan_parquet / polars scan_parquet
       실험은 DuckDB, 서비스 팩트는 MariaDB 2층
  5. MCP (읽기 전용)
       list_tables, describe_table, query_tables. LIMIT 강제
  6. 벡터
       테이블/컬럼 설명만. 행 데이터 금지
  원본 parquet 보관. 재압축은 필요 시에만
```

## 단계별 권장

### 1. 이미 1층이면 파이프라인을 다시 돌리지 않는다

xlsx 경로는 “추출 → Parquet 1층 → SQL 2층”이다. 첨부 파일이 그 1층이면 **도착점**이다. 다시 calamine을 돌리거나 마크다운으로 풀지 않는다.

등록만 한다.

- 데이터셋 이름, Grain(한 행이 무엇인지)
- 파티션 키, 기간, 제품/차종
- `source_file` / `ingested_at` 유무
- 압축 codec, 파일 크기, 행 수

카탈로그에 올린 뒤 MCP가 바로 친다. 랜딩을 CSV로 내려 “다시 깨끗하게” 만들지 않는다. 타입·null·한글이 깨진다.

### 2. 입고 검증

확장자가 `.parquet`여도 깨진 파일·부분 쓰기가 있다. 스캔 전에 풋터를 본다.

- 매직 `PAR1`, 스키마 필드명·타입
- row group이 과하게 작거나 하나가 전체를 삼키지 않는지
- 압축: snappy/zstd/gzip. 코덱이 런타임에 없으면 실패로 남긴다
- Hive 파티션: 디렉터리명과 컬럼이 일치하는지. `period=2024-09`가 파일 안 값과 다른지
- 스냅샷 vs 원장: 04와 같다. 월보 parquet를 UNION하지 않는다

프로파일 JSON(컬럼, 타입, null, 샘플 5행)만 LLM에 준다. 원본 파일을 채팅에 올리지 않는다.

### 3. 스캔만, 로드하지 않는다

100MB 이상은 xlsx와 같다. `read_parquet`로 메모리에 올리지 않고 `scan_parquet` / `parquet_scan`으로 필요한 컬럼만 읽는다. 파티션 prune이 되면 전 파일을 열지 않는다.

pandas 기본 경로는 금지에 가깝다. dtype 추론·객체 컬럼으로 메모리가 폭주한다. 실험·서비스 조회는 DuckDB SQL이 본체다.

### 4. 중첩이어도 RAG가 아니다

품질 덤프에 `struct`, `list<struct>`, `map`이 있다. JSON 문서 배열을 parquet에 담은 경우도 있다. 그래도 가족 C다.

- flatten 컬럼을 1층에 파생하거나, DuckDB가 중첩을 조회한다
- 원인/대책 긴 문자열 칸이 있으면 04처럼 **복제해서** RAG할 수 있다. 원 컬럼은 남긴다
- 리스트 원소 하나하나를 Milvus 청크로 쪼개 집계를 대체하지 않는다

문서형 JSON 원본이면 [20-json.md](20-json.md) 분기를 먼저 타는 편이 낫다. 이미 parquet면 여기서 스캔한다.

### 5. MCP와 2층

도구는 04와 같다. 파일이 parquet라는 이유로 새 도구를 만들지 않는다.

1. `list_tables(product, period)`
2. `describe_table(name)` — 컬럼, 단위, Grain, 파티션
3. `query_tables(sql)` — 읽기 전용, 허용 스키마, LIMIT

2층 팩트(`claim_event`, `monthly_quality_kpi`)가 있으면 MariaDB가 서비스다. parquet 1층은 재처리·검증용으로 남긴다. `SELECT *`를 Codex에 열지 않는다.

## 흔한 실패

- parquet를 텍스트로 열어 바이너리 청크가 쌓인다
- 1층 랜딩을 CSV로 내려 utf-8/cp949가 섞인다
- Hive 파티션을 무시하고 전 기간 UNION → 월보 중복 집계
- 중첩 struct를 JSON 문자열로 dump 해 임베딩한다
- 코덱(zstd) 없는 런타임에서 0행을 “빈 표”로 인덱싱한다
- pandas로 전 컬럼 load → OOM
- 파일명 = 테이블명으로 3,100개를 만든다

## 하지 말 것

- Parquet → CSV → 다시 Parquet
- 행 단위 임베딩으로 “비슷한 클레임” 검색을 집계 대신 쓰기
- Docling / 마크다운 표 경로
- 원본 parquet 삭제
- 스키마를 맞추려고 컬럼을 임의 drop
- 외부에 원장 parquet 업로드

parquet는 변환 대상이 아니라 **이미 적재된 표**다. 검증하고 쿼리한다.

## 인접 포맷

- `.xlsx` → [04-xlsx.md](04-xlsx.md). 이 문서의 주 생산자. 스트리밍 추출 후 여기로 온다.
- `.csv` → [06-csv.md](06-csv.md). 인코딩만 잡고 바로 parquet.
- `.cell` → [37-cell.md](37-cell.md). 한셀 → xlsx → 04 → 여기.
- JSON 배열 → [20-json.md](20-json.md). 레코드면 같은 1층.
- 슬라이드 `.pptx` / `.show` → [07-pptx.md](07-pptx.md), [38-show.md](38-show.md). 가족 D. parquet에 넣지 않는다.
- 도면 `.dwg` / `.dxf` → [35-dwg.md](35-dwg.md), [36-dxf.md](36-dxf.md). 가족 H. 표제 메타만 정형 컬럼이 될 수 있다.
