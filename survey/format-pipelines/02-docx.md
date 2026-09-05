# DOCX 권장 파이프라인

- 배경: 시장품질 RAG/MCP에서 Word(`.docx`, 가족 A)를 어떻게 넣을 것인가. 약 3,100건 중 8D·대책서.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`, `../docx-pipeline.md`

## 결론

`.docx`는 엑셀처럼 SQL로 빼지 말고, PDF처럼 레이아웃 모델을 돌리지도 않는다. Word 스타일 트리를 살린 채 Docling JSON으로 읽고, 표만 따로 둔다. PDF 변환은 기본 경로가 아니다.

권장 한 줄:

```
.docx → 시그니처(ZIP/OOXML) → Docling SimplePipeline → JSON 원본 보관
      → HybridChunker(contextualize + 표 분리, repeat_table_header=True) → Milvus
      → MCP: outline / section / table
```

| 선택 | 판단 |
|---|---|
| 마크다운 dump 후 토큰 자르기 | 하지 말 것 |
| PDF로 변환 후 StandardPdfPipeline | 기본 경로 아님. 구조가 깨짐 |
| python-docx만으로 텍스트 dump | 표·제목 계층이 약함 |
| Docling JSON + HybridChunker | **기본 경로** |
| 표를 본문 문장에 섞어 임베딩 | 하지 말 것. 표는 별도 객체 |
| xlsx처럼 MariaDB/Parquet 적재 | 해당 없음. 서술 문서 |

PDF용 `StandardPdfPipeline`(layout, TableFormer, GPU)은 `.docx`에 쓰지 않는다. Word는 XML이라 **SimplePipeline**이 맞고, 더 싸고 더 정확하다.

## 권장 파이프라인

```
업로드 .docx
  1. 포맷 검증
       ZIP/OOXML 아니면 .doc / .rtf 게이트로 보냄
  2. Docling SimplePipeline
       DoclingDocument JSON 저장 (손실 없는 원본)
  3. 구조 분해
       목차(Heading) / 본문 / 표 / 그림 / 헤더·푸터 메타
  4. 청크
       HybridChunker + chunker.contextualize(chunk)
       표는 CSV/Markdown 별도 청크, repeat_table_header=True
  5. 메타데이터
       제품, 차종, 품번, 문서유형, 기간, 섹션 경로
  6. 인덱싱
       본문·표 청크 → Milvus (하이브리드 + 필터)
  7. MCP
       get_outline, get_section, get_table, search_passages
```

원본 `.docx`와 JSON은 둘 다 보관한다. 청크만 남기면 청킹 전략을 바꿀 때 다시 파싱해야 한다. LibreOffice는 `.docx` 기본 경로에 필요 없다.

## 단계별 권장

### 1. 파싱: JSON을 남기고 마크다운은 쓰지 말 것

Docling은 Word를 두 가지로 내보낸다.

- **JSON (`DoclingDocument`)**: 제목, 표, 리스트, 캡션이 객체로 남음
- **Markdown**: 표 병합, 계층, 캡션이 손실됨

시장품질 8D·대책서는 제목 계층이 곧 검색 단위다. `1. 현상 → 2. 원인 → 3. 대책`이 헤딩으로 살아 있어야 `get_section("대책")`이 된다.

Word 스타일이 핵심이다. `제목 1/2/3`이 있으면 HybridChunker가 섹션을 자른다. 굵은 글씨만 제목처럼 쓴 문서는 통짜 본문이 된다. 표본에서 Heading 사용 비율을 먼저 본다.

### 2. 청크: HybridChunker + 제목 경로

고정 길이 슬라이딩 윈도우는 Word에서 제일 먼저 버린다.

```text
[문서] 2024년 OO 차종 시장품질 8D
[섹션] 3. 근본원인 > 3.2 공정 조건
[본문] ...
```

- 임베딩 토크나이저 기준 토큰 상한
- 같은 제목 아래 작은 조각은 병합 (`merge_peers=True`)
- 표가 길면 행 단위로 자르되 헤더를 각 조각에 반복 (`repeat_table_header=True`)
- 임베딩 입력은 `chunk.text`가 아니라 `chunker.contextualize(chunk)`다. 제목 경로가 여기에 붙는다.

검색은 작은 청크, 답변은 부모 섹션을 넣는 parent-child가 담당자 질의에 맞다.

### 3. 표: 본문과 분리

- `TableItem` → DataFrame/CSV로 직렬화
- 청크 타입을 `text` / `table`로 구분
- 캡션·바로 위 제목을 표 메타에 붙임
- 셀 안에 원인/대책처럼 긴 글이 있으면 그 열만 텍스트 청크로 복제

같은 양식 표가 수백 문서에 반복되면 그때 2층 SQL로 올린다. `.docx` 전체를 DB화할 필요는 없다. xlsx 행을 Milvus에 넣는 것과 같은 실수를 하지 않는다.

### 4. 헤더·푸터·품번

Docling은 머리글/바닥글이 약할 수 있다. 품번·문서번호가 여기 있으면 `python-docx`로 헤더/푸터만 추가로 긁어 메타데이터에 넣는다. 본문 청크에 반복시키지 않는다.

페이지 번호는 Word에 원래 없다. 인용은 `파일명 + 섹션 경로`다.

### 5. MCP

Codex CLI MCP는 검색 하나가 아니다.

1. `list_documents(product, doc_type, period)`
2. `get_outline(doc_id)` — Heading 트리
3. `get_section(doc_id, heading_path)` — 답변 근거
4. `get_table(doc_id, table_id)`
5. `search_passages(query, filters)` — 하이브리드 + rerank

3,100건을 필터 없이 의미 검색만 하면 다른 차종 8D가 올라온다.

## 흔한 실패

- Heading 없이 굵은 글씨만 써서 통짜 본문이 된다
- 표를 마크다운 파이프로 평탄화해 숫자가 틀린다
- 헤더 품번이 모든 청크에 반복된다
- ZIP이 아닌 `.docx`를 SimplePipeline에 넣어 실패 원인을 가린다
- PDF 변환으로 스타일 트리를 버린다

## 하지 말 것

- `.docx`를 통째로 임베딩하는 것
- 청크 크기만 200/500으로 튜닝해서 해결하려는 것
- 모든 Word 표를 MariaDB/Parquet로 넣는 것
- 변환 실패·빈 문서를 인덱싱하는 것
- 답변에 섹션 경로를 안 남기는 것
- PDF로 바꿔 가족 B에 넣는 것

## 인접 포맷

- `.doc`는 입고에서 LibreOffice 게이트 후 이 파이프라인과 동일. Docling 내장 변환은 쓰지 않는다. `03-doc.md`
- `.rtf`도 LibreOffice → DOCX 후 여기로. `16-rtf.md`
- PDF는 가족 B. Word를 PDF로 보내지 않는다. `01-pdf.md`
