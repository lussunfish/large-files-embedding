# ODT 권장 파이프라인

- 배경: 시장품질 RAG/MCP에서 OpenDocument 텍스트(`.odt`, 가족 A)를 어떻게 넣을 것인가. 약 3,100건 중 8D·대책서의 LibreOffice 저장본.
- 관련 문서: `../docx-pipeline.md`, `../market-quality-rag-improvement.md`, `README.md`

## 결론

`.odt`는 Word와 같은 서술 문서다. SQL로 빼지 않는다. Docling에 네이티브 `OdtDocumentBackend`(odfdo)가 있다. **SimplePipeline JSON + HybridChunker를 먼저** 탄다. LibreOffice `--convert-to docx`는 폴백이다. 기본 입고에서 docx 변환을 요구하지 않는다. PDF 변환은 기본이 아니다. 표는 본문과 분리한다. 원본을 보관한다.

권장 한 줄:

```
.odt → 시그니처(ZIP + mimetype=text) → Docling OdtDocumentBackend (odfdo)
     → SimplePipeline JSON 원본 보관
     → HybridChunker(contextualize + 표 분리) → Milvus
     → MCP: outline / section / table
```

| 선택 | 판단 |
|---|---|
| 마크다운 dump 후 토큰 자르기 | 하지 말 것 |
| PDF로 변환 후 StandardPdfPipeline | 기본 경로 아님. 구조가 깨짐 |
| unzip 후 XML 태그 임베딩 | 하지 말 것 |
| Docling `OdtDocumentBackend` (odfdo) + SimplePipeline | **기본 경로** |
| LibreOffice → `.docx` 후 02 | 폴백. 기본이 아님 |
| 표를 본문 문장에 섞어 임베딩 | 하지 말 것. 표는 별도 객체 |
| xlsx/ods처럼 Parquet/SQL 적재 | 해당 없음. 서술 문서 |
| 원본 삭제 후 변환본만 | 하지 말 것 |

PDF용 `StandardPdfPipeline`(layout, TableFormer, GPU)은 `.odt`에 쓰지 않는다. ODT는 ZIP/XML이라 **SimplePipeline**이 맞고, 더 싸고 더 정확하다. `OdtDocumentBackend`가 실패하면 LibreOffice → `.docx` 후 02다. 처음부터 convert-to-docx를 기본으로 두지 않는다.

## 권장 파이프라인

```
업로드 .odt
  1. 포맷 검증
       ZIP + application/vnd.oasis.opendocument.text → ODT
       spreadsheet mimetype → 24-ods
       OOXML word/          → 02-docx
       OLE                  → 03-doc
  2. Docling SimplePipeline
       OdtDocumentBackend (odfdo) → DoclingDocument JSON 저장
  3. 폴백
       네이티브 백엔드 실패 → soffice --headless → .docx → 02
       convert-to-docx는 기본이 아님. PDF 변환도 기본 아님
  4. 구조 분해
       목차(Heading) / 본문 / 표 / 그림 / 헤더·푸터 메타
  5. 청크
       HybridChunker + heading breadcrumb
       표는 CSV/Markdown 별도 청크, 헤더 반복
  6. 메타데이터
       제품, 차종, 품번, 문서유형, 기간, 섹션 경로
       source_format=odt
  7. 인덱싱
       본문·표 청크 → Milvus (하이브리드 + 필터)
  8. MCP
       get_outline, get_section, get_table, search_passages
```

원본 `.odt`와 JSON은 둘 다 보관한다. 청크만 남기면 청킹 전략을 바꿀 때 다시 파싱해야 한다. LibreOffice는 폴백에만 쓴다. 기본 경로에서 docx 변환을 요구하지 않는다.

## 단계별 권장

### 1. 파싱: JSON을 남기고 XML/마크다운은 쓰지 말 것

ODS와 같이 ZIP을 풀어 `content.xml`을 청크하지 않는다. 태그는 구조이지 본문이 아니다.

Docling export:

- **JSON (`DoclingDocument`)**: 제목, 표, 리스트, 캡션이 객체로 남음
- **Markdown**: 표 병합, 계층, 캡션이 손실됨

시장품질 8D·대책서는 `1. 현상 → 2. 원인 → 3. 대책`이 헤딩으로 살아 있어야 `get_section("대책")`이 된다. ODT 스타일(`Heading 1/2/3`)이 핵심이다. 굵은 글씨만 제목처럼 쓴 문서는 통짜 본문이 된다.

### 2. 청크: 02와 동일

고정 길이 슬라이딩 윈도우는 버린다.

```text
[문서] 2024년 OO 차종 시장품질 8D
[섹션] 3. 근본원인 > 3.2 공정 조건
[본문] ...
```

- 임베딩 토크나이저 기준 토큰 상한
- 같은 제목 아래 작은 조각은 병합 (`merge_peers=True`)
- 표가 길면 행 단위로 자르되 헤더를 각 조각에 반복 (`repeat_table_header=True`)
- 임베딩 입력은 `chunker.contextualize(chunk)`다

검색은 작은 청크, 답변은 부모 섹션을 넣는 parent-child가 담당자 질의에 맞다.

### 3. 표는 분리, 문서는 SQL이 아니다

- `TableItem` → DataFrame/CSV로 직렬화
- 청크 타입을 `text` / `table`로 구분
- 캡션·바로 위 제목을 표 메타에 붙임
- 셀 안에 원인/대책처럼 긴 글이 있으면 그 열만 텍스트 청크로 복제

같은 양식 표가 수백 문서에 반복되면 그때 2층 SQL로 올린다. `.odt` 전체를 DB화하지 않는다. ODS/xlsx 행을 Milvus에 넣는 것과 반대 실수도 하지 않는다. 표 **행 전체**를 벡터 원장으로 쓰지 않는다.

### 4. PDF는 기본이 아니다

ODT→PDF는 스타일 트리를 버리고 가족 B로 보낸다. 레이아웃·스탬프·비전 검색이 필요할 때만. 기본 입고는 JSON이다.

폴백 LibreOffice는 `--convert-to docx`다. 한글 폰트, 워커 하나, 타임아웃·`UserInstallation` 격리는 [03-doc.md](03-doc.md)와 같다. 네이티브 백엔드가 되는 파일에 변환을 먼저 걸지 않는다.

### 5. MCP

Codex CLI MCP는 검색 하나가 아니다.

1. `list_documents(product, doc_type, period)`
2. `get_outline(doc_id)` — Heading 트리
3. `get_section(doc_id, heading_path)`
4. `get_table(doc_id, table_id)`
5. `search_passages(query, filters)` — 하이브리드 + rerank

3,100건을 필터 없이 의미 검색만 하면 다른 차종 8D가 올라온다. 인용은 `파일명 + 섹션 경로`다.

## 흔한 실패

- `content.xml`을 풀어 태그가 청크에 남는다
- Heading 없이 굵은 글씨만 써서 통짜 본문이 된다
- 표를 마크다운 파이프로 평탄화해 숫자가 틀린다
- ODS로 오분류해 Parquet에 문장을 넣는다
- PDF 변환으로 스타일 트리를 버린다
- 변환본만 남기고 원본 `.odt`를 지운다

## 하지 말 것

- `.odt`를 통째로 임베딩하는 것
- ZIP 엔트리를 19-xml로 보내는 것
- 모든 ODT 표를 MariaDB/Parquet로 넣는 것
- 변환 실패·빈 문서를 인덱싱하는 것
- 답변에 섹션 경로를 안 남기는 것
- PDF로 바꿔 가족 B에 넣는 것 (기본 경로)
- 네이티브 백엔드가 되는 파일에 convert-to-docx를 기본으로 거는 것

## 인접 포맷

- `.docx` → [02-docx.md](02-docx.md). 이 문서의 청크 규칙
- `.doc`/`.rtf` → [03-doc.md](03-doc.md), [16-rtf.md](16-rtf.md). LibreOffice 후 가족 A
- `.ods` → [24-ods.md](24-ods.md). 같은 ODF ZIP, 가족 C (RAG 금지)
- `.odp` → [26-odp.md](26-odp.md). 슬라이드
- PDF는 가족 B. ODT를 PDF로 보내지 않는다. [01-pdf.md](01-pdf.md)
