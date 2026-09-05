# XML 권장 파이프라인

- 배경: 시장품질 XML은 클레임 리스트 내보내기(정형)와 보고서/OOXML(문서)가 섞인다. 원문 태그를 청크하지 않는다. 대용량은 스트리밍이다.
- 관련 문서: `../excel-to-sql-decision.md`, `../xlsx-20-samples-layer1.md`, `README.md`

## 결론

XML은 한 파이프라인이 아니다. 레코드형이면 flatten → Parquet/SQL, 문서형이면 트리→섹션이다. OOXML은 여기가 아니다. Docling 범용 XML 백엔드는 없다(USPTO/JATS/XBRL/DocLang만). XXE는 끈다. 거대 XML은 DOM이 아니라 iterparse다.

| 선택 | 판단 |
|---|---|
| raw XML 태그를 Milvus 청크 | 하지 말 것 |
| 레코드 XML → XPath flatten → Parquet/SQL | **정형 분기 (a)** |
| 문서 XML → 섹션 트리 (서술 RAG) | **문서 분기 (b)** |
| 외부 엔티티(XXE) 허용 | 하지 말 것 |
| 거대 XML을 DOM 전체 로드 | 하지 말 것. iterparse |
| OOXML(xlsx/docx)을 여기로 | 하지 말 것. 04/02가 담당 |
| Docling 범용 XML 백엔드 | 없음. USPTO/JATS/XBRL/DocLang만 |
| 파일마다 SQL 테이블 | 하지 말 것 |

권장 한 줄:

```
xml → 시그니처/스키마 → (a) 레코드면 XPath flatten → Parquet → SQL
                      → (b) 문서면 트리→섹션 RAG
     태그 청크 금지. XXE 끄고, 대용량은 iterparse. Docling 범용 XML 없음
```

## 권장 파이프라인

```
업로드 .xml
  1. 안전
       외부 엔티티·DTD resolve 비활성 (XXE)
  2. 시그니처
       [Content_Types].xml / xl/ / word/  → OOXML. 확장자 복원 후 02/04
       클레임/리스트 반복 노드            → (a) 정형
       보고서·섹션 헤딩형                 → (b) 문서
  3a. 정형
       XSD/스키마 또는 반복 경로 추론
       streaming iterparse로 레코드 단위 flatten
       Parquet 1층(원본 경로 컬럼) → SQL 2층 → MCP
  3b. 문서
       트리에서 섹션/문단/표만 추출
       태그 제거한 텍스트 + 경로 breadcrumb
       HybridChunker → Milvus
  4. 공통
       벡터에는 정형이면 카탈로그만
       긴 서술 필드(원인/대책)는 RAG 복제, 테이블에서 삭제 금지
       MCP 정형: list_tables / describe_table / query_tables (읽기 전용)
```

## 단계별 권장

### 1. XXE와 대용량

사내 XML도 외부 엔티티를 끈다.

- lxml: `resolve_entities=False`, 네트워크 로더 금지
- Python `xml.etree` 기본 파서는 외부 엔티티에 약하다. 입고에 쓰지 말 것
- defusedxml 또는 동등한 가드로 DTD/ENTITY를 막는다
- 100MB급은 `iterparse`(start/end 이벤트). `parse()` DOM은 OOM이다
- 원소를 처리한 뒤 부모에서 지워 메모리를 묶는다

### 2. 분기 기준

정형 (a)에 가깝다:

- 같은 자식 노드가 수백~수천 반복 (`Claim`, `Row`, `Item`)
- 속성/엘리먼트가 컬럼처럼 고정
- ERP/MES/클레임 시스템 내보내기, 표형 덤프

문서 (b)에 가깝다:

- 제목, 문단, 자유 텍스트가 본체
- 일부 한글/보고서 XML
- OOXML은 이미 02/04. 여기 넣지 않는다
- Docling 범용 XML 백엔드는 없다. USPTO/JATS/XBRL/DocLang만. 클레임 XML을 거기에 넣지 않는다

애매하면 프로파일러가 반복 노드 카디널리티를 센다. 반복이 지배적이면 (a). LLM에는 스키마/경로 프로필만 준다. XML 원문 100MB를 채팅에 올리지 않는다.

### 3. 정형 flatten

- 반복 경로를 Grain으로 둔다. 한 행 = 클레임 1건
- 중첩은 `claim.part.no`처럼 경로를 컬럼명으로
- 1층은 원본 경로 컬럼을 유지. 파일당 테이블 금지
- `source_file`, `report_period`, `ingested_at`을 붙인다. 스냅샷이면 UNION하지 않는다
- 이후는 04와 같다: Parquet → curated SQL, MCP `list_tables` / `describe_table` / `query_tables`

### 4. 문서 트리

- 태그 이름·속성을 본문 청크에 넣지 않는다
- 섹션 경로는 메타로만 (`/보고서/원인/대책`)
- 표 노드는 표 객체로 분리한다
- 본문이 사실상 엑셀 덤프면 (a)로 되돌린다

## 흔한 실패

- `<Claim>` 수천 개를 통 XML 문자열로 임베딩
- XXE로 로컬 파일/네트워크가 파서에 노출
- `parse()`로 100MB DOM
- xlsx 내부 `[Content_Types].xml`을 문서 XML로 인덱싱
- 네임스페이스를 무시해 XPath가 0건
- 중첩 리스트를 한 컬럼 JSON 문자열로만 넣고 집계 불가
- 원인/대책 엘리먼트를 flatten 후 drop

## 하지 말 것

- XML 원문을 마크다운 코드블록으로 청크
- 외부 엔티티·XInclude 허용
- 파일마다 SQL 테이블
- OOXML을 19에서 재파싱
- 클레임 XML을 Docling USPTO/JATS/XBRL 백엔드에 넣기
- 원인/대책 엘리먼트를 flatten 후 삭제
- `SELECT *`를 Codex에 열어 두기

## 인접 포맷

- `.xlsx`/`.docx` = ZIP+XML → 04/02. 여기 아님
- `.hwpx` → 10. ZIP/XML이지만 한글 문서 가족
- `.json` → 20. 같은 두 갈래(레코드 vs 문서)
- `.csv` → 이미 flatten된 (a). 06으로 합류
- SpreadsheetML `.xml` → (a) 또는 시그니처 후 04 계열
