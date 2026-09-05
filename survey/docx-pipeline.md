# .docx 권장 파이프라인

- 배경: 시장품질 문서 RAG/MCP에서 Word(`.docx`)를 어떻게 넣을 것인가
- 관련 문서: `market-quality-rag-improvement.md`, `doc-format-handling.md`, `format-pipelines/02-docx.md`
- 재검토: 2026-09-05

## 결론

`.docx`는 엑셀처럼 SQL로 빼지 말고, PDF처럼 레이아웃 모델을 돌리지도 않는다. Word 스타일 트리를 살린 채 Docling JSON으로 읽고, 표만 따로 두는 경로가 맞다.

권장 한 줄:

```
.docx → 시그니처 확인 → Docling SimplePipeline → JSON 원본 보관
      → HybridChunker(제목 경로 + 표 분리) → Milvus
      → MCP는 search가 아니라 outline / section / table
```

| 선택 | 판단 |
|---|---|
| 마크다운으로보낸 뒤 토큰 자르기 | 하지 말 것 |
| PDF로 변환 후 Docling PDF 파이프라인 | 기본 경로 아님. 구조가 깨짐 |
| python-docx만으로 텍스트 dump | 표·제목 계층이 약함 |
| Docling JSON + HybridChunker | **기본 경로** |
| 표를 본문 문장에 섞어 임베딩 | 하지 말 것. 표는 별도 객체 |
| xlsx처럼 MariaDB 적재 | 해당 없음. 서술 문서 |

PDF용 `StandardPdfPipeline`(layout 모델, TableFormer, GPU)은 `.docx`에 쓰지 않는다. Word는 XML이라 **SimplePipeline**이 맞고, 더 싸고 더 정확하다.

## 권장 파이프라인

```
업로드 .docx
  1. 포맷 검증
       ZIP/OOXML 아니면 .doc 게이트로 보냄
  2. Docling SimplePipeline
       DoclingDocument JSON 저장 (손실 없는 원본)
  3. 구조 분해
       목차(Heading) / 본문 / 표 / 그림 / 헤더·푸터 메타
  4. 청크
       HybridChunker + heading breadcrumb
       표는 CSV/Markdown 별도 청크, 헤더 반복
  5. 메타데이터
       제품, 차종, 문서유형, 기간, 파일경로, 섹션 경로
  6. 인덱싱
       본문·표 청크 → Milvus (하이브리드 + 필터)
       문서/섹션 요약 → 상위 인덱스
  7. MCP
       list_documents, get_outline, get_section, get_table, search_passages
```

원본 `.docx`와 JSON은 둘 다 보관한다. 청크만 남기면 나중에 청킹 전략을 바꿀 때 파일을 다시 파싱해야 한다.

## 단계별 권장

### 1. 파싱: JSON을 남기고 마크다운은 쓰지 말 것

Docling은 Word를 두 가지로 내보낸다.

- **JSON (`DoclingDocument`)**: 제목, 표, 리스트, 캡션이 객체로 남음
- **Markdown**: RAG 시작용으로는 편하지만 표 병합, 계층, 캡션이 손실됨

시장품질 8D·대책서는 제목 계층이 곧 검색 단위다. `1. 현상 → 2. 원인 → 3. 대책`이 헤딩으로 살아 있어야 `get_section("대책")`이 된다.

Word 스타일이 핵심이다. `제목 1/2/3`이 살아 있으면 HybridChunker가 섹션을 자른다. 굵은 글씨만 제목처럼 쓴 문서는 통짜 본문이 된다. 표본에서 Heading 사용 비율을 먼저 보는 것이 좋다.

LibreOffice는 `.docx` 기본 경로에 필요 없다. DrawingML(SmartArt, 차트) 렌더에만 켠다. 켤 때도 timeout과 UserInstallation을 건다. 막대/원/선 차트는 Docling chart extraction이 VLM보다 싸다.

### 2. 청크: HybridChunker + 제목 경로

고정 길이 슬라이딩 윈도우는 Word에서 제일 먼저 버릴 습관이다.

```text
[문서] 2024년 OO 차종 시장품질 8D
[섹션] 3. 근본원인 > 3.2 공정 조건
[본문] ...
```

이런 breadcrumb를 청크 앞에 붙인다. Docling `HybridChunker.contextualize(chunk)`가 하는 일이다.

- 임베딩 토크나이저 기준으로 토큰 상한
- 같은 제목 아래 작은 조각은 병합 (`merge_peers=True`)
- 표가 길면 행 단위로 자르되 **헤더를 각 조각에 반복** (`repeat_table_header=True`)
- Anthropic contextual retrieval(청크마다 LLM 설명)은 비용이 크다. Word는 헤딩 경로만으로도 대부분 충분하다.

본문은 검색용 작은 청크, 답변 때는 부모 섹션을 넣는 **parent-child**가 담당자 질의에 잘 맞다. “이 이슈 대책이 뭐야”는 문장 하나가 아니라 섹션 전체가 필요하기 때문이다.

### 3. 표: 본문과 분리

Word 표는 엑셀 원장이 아니지만, 평탄화하면 숫자가 틀리다.

- `TableItem` → DataFrame/CSV로 직렬화
- 청크 타입을 `text` / `table`로 구분
- 캡션·바로 위 제목을 표 메타에 붙임 (`표 3. 클레임 건수 by 고장모드`)
- 행이 많으면 표 요약 1개 + 행 그룹 청크
- 셀 안에 원인/대책처럼 긴 글이 있으면 그 열만 텍스트 청크로 복제

표가 “이 문서 안의 작은 집계”면 여기까지면 된다. 같은 양식 표가 수백 문서에 반복되면 그때 2층 SQL로 올린다. `.docx` 전체를 DB화할 필요는 없다.

### 4. 그림·텍스트박스

품질 문서의 Pareto, 공정 사진, 스캔 표는 본문 XML에 숫자가 없다.

- 임베디드 이미지는 따로 저장
- 캡션이 있으면 캡션으로 검색
- 캡션이 없으면 VLM으로 한 줄 설명 + 숫자 추출
- 텍스트박스/머리글/바닥글은 Docling이 약할 수 있음. 문서번호·품번이 여기 있으면 `python-docx`로 헤더/푸터만 추가로 긁어 메타데이터에 넣기

페이지 번호는 Word에 원래 없다. 인용은 `파일명 + 섹션 경로`가 PDF의 페이지보다 정확하다.

### 5. 메타데이터

파일명과 첫 페이지에서 가능한 한 뽑는다.

- 제품 / 차종 / 품번
- 문서 유형: 8D, 월보, VOC, 대책서
- 기간, 작성 부서
- 섹션 경로, 표 인덱스
- `source_path`, `parser=docling`, `pipeline=simple`

Milvus 필터가 이 필드다. 3,100건을 매번 의미 검색만 하면 다른 차종 8D가 올라온다.

### 6. MCP

`.docx`용 도구는 검색 하나가 아니다.

1. `list_documents(product, doc_type, period)`
2. `get_outline(doc_id)` — Heading 트리
3. `get_section(doc_id, heading_path)` — 답변 근거
4. `get_table(doc_id, table_id)`
5. `search_passages(query, filters)` — 하이브리드 + rerank

Codex가 목차를 보고 해당 장만 읽게 하는 것이, top-5 문장 RAG보다 정확하다.

## PDF로 바꾸지 않는 이유

`.docx → PDF → Docling PDF`는 레이아웃 모델을 타서 느리고, Heading 정보가 픽셀로부터 다시 추정되며 정확도가 떨어진다. Word가 이미 준 구조를 버리는 셈이다.

PDF가 이득인 경우는 제한적이다. 도장, 스캔 페이지, 차트 비전 검색이 필요할 때뿐이다.

## 표본에서 먼저 볼 것

`.docx` 20개면 파이프라인 고정에 충분하다.

1. Heading 스타일 사용 여부
2. 표 개수, 병합 셀, 표 안 긴 서술
3. 헤더/푸터에 품번·문서번호가 있는지
4. 임베디드 엑셀/차트
5. 이미지가 본문 숫자인지 장식인지

Heading이 거의 없으면, 파서 다음에 **제목 복원 규칙**(번호 매기기 `1.`, `1.1`, `■ 대책`)을 한 겹 두는 것이 Docling 교체보다 효과가 크다.

## 하지 말 것

- `.docx`를 통째로 임베딩
- 청크 크기만 200/500으로 튜닝해서 해결하려는 것
- 모든 Word 표를 MariaDB로 넣는 것
- 변환 실패·빈 문서를 인덱싱하는 것
- 답변에 섹션 경로를 안 남기는 것

`.doc`는 LibreOffice로 `.docx`가 된 뒤 **이 파이프라인과 동일**하다. 차이는 입고 게이트뿐이고, 파싱 이후는 공유하는 것이 맞다.
