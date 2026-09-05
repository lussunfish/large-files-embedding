# YAML 권장 파이프라인

- 배경: 시장품질 YAML은 클레임 레코드 덤프와 중첩 설정/문서가 섞인다. JSON(20)과 같은 두 갈래다. 원문 100MB를 한 청크로 넣지 않는다.
- 관련 문서: `../excel-to-sql-decision.md`, `../xlsx-20-samples-layer1.md`, `README.md`

## 결론

배열/레코드면 가족 C → Parquet/SQL, 중첩 설정·문서면 가족 E → 경로를 살린 텍스트다. 태그를 실행하지 않는다. Docling 범용 YAML 백엔드는 없다. 스키마는 코드가 추론하고, LLM에는 프로필만 준다.

| 선택 | 판단 |
|---|---|
| YAML 파일 전체를 한 청크로 임베딩 | 하지 말 것 |
| 레코드 리스트 → DataFrame/SQL | **정형 분기 (a)** |
| 중첩 설정/문서 → 경로 유지 텍스트 | **문서 분기 (b), 가족 E** |
| `yaml.load` / unsafe 태그 실행 | 하지 말 것 |
| 100MB를 메모리에 로드 | 하지 말 것 |
| Docling 범용 YAML 백엔드 | 없음. 이중 분기 유지 |
| 파일마다 SQL 테이블 | 하지 말 것 |

권장 한 줄:

```
yaml/yml → 시그니처·인코딩 → SafeLoader (태그 실행 금지)
        → (a) 레코드면 DataFrame → Parquet → SQL
        → (b) 중첩 문서면 path 유지 텍스트 (가족 E)
     원문 통째 임베딩 금지. 100MB는 스트리밍/거부. Docling 범용 YAML 없음
```

## 권장 파이프라인

```
업로드 .yaml / .yml
  1. 시그니처
       멀티문서(---) / 리스트 / 단일 맵 / 위조 확장자
       JSON이면 20, 마크다운 프론트매터면 14
  2. 안전·인코딩
       SafeLoader만. !!python / !!apply 거부
       utf-8-sig / utf-8 / cp949
  3. 스트리밍 프로파일
       키 경로, 타입, 리스트 길이
       LLM에는 스키마 JSON만 (원문 100MB 금지)
  4a. 레코드 리스트
       최상위 [] 또는 items/records
       flatten → Parquet 1층 → SQL 2층
  4b. 중첩 문서·설정
       경로를 키로 (report.cause)
       긴 문자열만 RAG, 숫자는 typed extract
  5. MCP
       정형: list_tables / describe_table / query_tables
       문서: outline / section / search
  6. 벡터
       카탈로그 또는 서술 필드만. YAML 원문 금지
```

## 단계별 권장

### 1. 태그를 실행하지 않는다

PyYAML `load()`는 `!!python/object/apply`로 코드를 돌린다. 입고는 `safe_load` / `SafeLoader`만 쓴다.

- 커스텀 태그, `!!binary` 큰 블롭, 앵커 폭탄(alias 폭증)은 실패 큐
- 외부 include·파일 경로 태그를 따라가지 않는다 (로컬 파일 노출)
- ruamel.yaml도 안전 모드. `unsafe_load` 금지

인코딩은 한국 덤프에서 cp949가 섞인다. utf-8만 가정하면 키가 깨져 스키마가 갈라진다.

### 2. JSON과 같은 두 갈래

정형 (a)에 가깝다:

- 최상위가 객체 리스트, 또는 `items` / `records` / `data`
- 키가 컬럼, 값이 스칼라 위주
- 클레임 원장·검사 결과 dump

문서 (b)에 가깝다:

- 키가 섹션이고 값이 긴 문자열·중첩 맵
- 매핑 설정, `mapping.yml`, 품질 절차 초안
- MD 프론트매터만 있으면 14로 되돌린다

애매하면 프로파일러가 리스트 카디널리티를 센다. 반복이 지배적이면 (a). 원문 100MB를 채팅에 올리지 않는다.

### 3. 정형 분기 (a)

- `json_normalize`에 넣기 전에 앵커를 펼친다. 순환 앵커는 자른다
- 1층은 원본 키 유지. 파일당 테이블 금지
- `source_file`, `report_period`, `ingested_at`. 월보성 덤프는 UNION하지 않는다
- 이후는 04/20과 동일. 숫자는 SQL, MCP는 읽기 전용 세 도구
- 멀티문서 `---`는 문서마다 레코드 묶음. 한 파일 한 테이블이 아니다

### 4. 문서 분기 (b)

가족 E다. Docling 범용 YAML 백엔드는 없다. PDF 파이프라인도 쓰지 않는다.

- 경로를 breadcrumb로: `report > 원인 > 대책`
- 숫자 필드는 typed extract로 SQL 후보에 따로
- 원문 YAML을 코드펜스 청크에 넣지 않는다
- 표형 리스트가 안에 있으면 그 경로만 (a)로 승격
- 설정 파일은 검색보다 `get_section(path)`가 맞다

### 5. 100MB

YAML은 JSON보다 스트리밍이 어렵다. 100MB 단일 문서는 ijson 같은 길이 없다.

- 최상위 리스트면 문서 단위/원소 단위로 나눈다
- 중첩 거대 맵은 프로필만 남기고 원문 임베딩을 거부한다
- `yaml.load` 한 방은 OOM이다. 크기 상한을 먼저 본다

원인/대책이 문자열이어도 테이블에서 지우지 않는다. RAG로 복제만 한다.

## 흔한 실패

- `yaml.load`로 태그 실행·임의 코드
- 100MB `safe_load` OOM
- 파일 전체를 코드펜스로 임베딩
- cp949를 utf-8로 읽어 키가 갈라짐
- 앵커 반복을 행 복제로 착각해 건수가 폭증
- 설정 YAML을 클레임 원장 테이블로 적재
- JSON(20)과 다른 매퍼를 새로 짜다 스키마가 엇갈림

## 하지 말 것

- YAML을 Docling/마크다운으로 우회 (범용 YAML 백엔드 없음)
- 원문 전체를 Milvus에 1청크
- unsafe Loader, 커스텀 태그 실행
- 외부 include/URL을 따라가기
- 파일당 SQL 테이블
- 2층에서 서술 키를 drop
- 100MB YAML을 LLM 채팅에 업로드
- `SELECT *`를 Codex에 열어 두기

## 인접 포맷

- `.json` → [20-json.md](20-json.md). 같은 두 갈래. 형제 문서
- `.xml` 레코드 → [19-xml.md](19-xml.md) (a) flatten
- `.csv` → 이미 평탄. [06-csv.md](06-csv.md)
- `.md` 프론트매터 → 본문이 마크다운이면 [14-md.md](14-md.md)
- `.txt` → YAML이 아닌 산문이 `.yml`로 온 경우 [15-txt.md](15-txt.md)
- `.xlsx` 매핑 YAML은 이 문서 (b). 데이터 원장은 [04-xlsx.md](04-xlsx.md)
