# .pptx 권장 파이프라인

- 배경: 시장품질 월간보고·8D 요약·품질회의 자료를 RAG/MCP에 넣을 때 슬라이드 단위를 유지한다.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

`.pptx`는 가족 D다. 서술 Word처럼 섹션 트리를 타지 않고, **슬라이드 1장 = 청크 1개**가 기본 단위다. 제목·본문·발표자 노트·차트 캡션을 한 장에 묶는다. 전 슬라이드를 하나의 텍스트 덩어리로 평탄화하지 않는다.

Docling은 PPTX를 **네이티브**로 읽는다. 백엔드는 `python-pptx`다. PDF용 레이아웃 모델은 쓰지 않는다. 차트는 종류를 가른다. bar/pie/line은 Docling chart understanding enrichment(그림 → 표)를 쓰고, 사진·공정 이미지는 VLM 캡션을 남긴다.

권장 한 줄:

```
.pptx → 시그니처(ZIP/OOXML) 확인 → Docling PPTX 백엔드 (python-pptx)
      → 슬라이드 단위 청크(제목+본문+노트+차트캡션)
      → 표는 table 객체
      → bar/pie/line: Docling chart extraction (그림→표)
      → 사진·공정 이미지: VLM 캡션
      → Milvus (slide_index 필터)
      → MCP: list_slides / get_slide(n)
```

| 선택 | 판단 |
|---|---|
| 전 슬라이드를 한 blob으로 dump | 하지 말 것. 이슈가 섞인다 |
| PDF로 변환 후 StandardPdfPipeline | 기본 경로 아님. 시각 검색이 필요할 때만 |
| Docling PPTX + 슬라이드 청크 | **기본 경로** |
| bar/pie/line을 VLM 한 줄로만 처리 | 하지 말 것. chart understanding을 먼저 |
| 사진·공정 이미지를 차트 추출에 맡김 | 하지 말 것. VLM 캡션 |
| 차트 이미지를 무시하고 본문만 | 하지 말 것. 월보는 차트가 본체 |
| 슬라이드 표를 문장으로 평탄화 | 하지 말 것. table 객체로 유지 |
| python-pptx만으로 텍스트 dump | 보조. 노트·도형 누락이 잦다 |

## 권장 파이프라인

```
업로드 .pptx
  1. 포맷 검증
       ZIP/OOXML 아니면 .ppt 게이트로 보냄
  2. Docling PPTX 파싱 (python-pptx)
       슬라이드 / 셰이프 / 표 / 노트 / 임베디드 이미지 / 네이티브 차트
  3. 그림 분기
       bar/pie/line → chart understanding enrichment (PictureItem → 표)
       사진·공정·SmartArt → VLM 캡션
  4. 슬라이드 조립 (1장 = 1청크)
       [제목]
       [본문 불릿]
       [발표자 노트]
       [표 직렬화]
       [차트 표 또는 캡션]
  5. 메타데이터
       제품, 차종, 문서유형, 기간, slide_index, 슬라이드 제목
  6. 인덱싱
       슬라이드 청크 → Milvus (하이브리드 + slide_index)
       표 청크는 type=table 로 분리
  7. MCP
       list_slides, get_slide(n), search_passages, get_table
  원본 .pptx 와 파싱 JSON 을 둘 다 보관
```

## 단계별 권장

### 1. 파싱: 슬라이드 경계를 버리지 말 것

시장품질 덱은 한 장이 한 이슈인 경우가 많다. `현상 / 원인 / 대책 / 일정`이 연속 슬라이드다. 전 장을 이어 붙이면 “A품번 대책”이 “B품번 현상”과 같은 청크에 들어간다.

- 슬라이드 번호는 인용 단위다. Word의 섹션 경로와 같다.
- 발표자 노트에 원인·대책 서술이 있는 경우가 많다. 화면에 안 보인다고 버리지 않는다.
- 마스터/레이아웃의 반복 머리글·바닥글은 메타로만 남긴다. 매 청크에 반복 임베딩하지 않는다.

### 2. 청크: 제목 + 본문 + 노트 + 캡션

```text
[문서] 2024-09 OO 차종 시장품질 월간보고
[슬라이드] 12 / 원인분석 — 누유
[본문] ...
[노트] ...
[차트] Pareto: 누유 42%, 이음 21% ...
```

한 장이 임베딩 한도를 넘으면 같은 `slide_index` 안에서 본문/노트/표를 나눈다. 다른 슬라이드와 합치지 않는다.

### 3. 표와 차트

- 슬라이드 표는 `TableItem`으로 남긴다. CSV/Markdown으로 직렬화하되 헤더를 유지한다.
- **bar / pie / line**은 Docling chart understanding enrichment를 켠다. 그림으로만 두지 않고 `PictureItem.meta.tabular_chart.chart_data`를 표로 승격한다. 월보 Pareto·추세선이 여기 해당한다. VLM 한 줄 캡션의 대안이자 보완이다.
- python-pptx가 네이티브 차트 시리즈를 주면 그것도 표로 남긴다. 렌더 그림만 있는 차트는 enrichment가 담당한다.
- **사진·공정 이미지·SmartArt·그룹 도형**은 차트 추출 대상이 아니다. 텍스트 프레임을 모으고, 시각 관계가 본이면 VLM 캡션을 붙인다.
- scatter·area·복합 차트는 enrichment 범위 밖이다. 캡션이 있으면 캡션, 없으면 VLM + 숫자 OCR.

### 4. MCP

`search` 하나만 두지 않는다. Codex는 목차처럼 슬라이드 목록을 보고 해당 장만 읽는다.

1. `list_slides(doc_id)` — 번호, 제목, 차트 여부
2. `get_slide(doc_id, n)` — 본문+노트+표+캡션
3. `search_passages(query, filters)` — `slide_index` 필터
4. `get_table(doc_id, slide_index, table_id)`

인용은 `파일명 + 슬라이드 n`이다.

### 5. PDF로 가는 경우

기본은 PPTX 구조 파싱이다. PDF 변환은 아래만 해당한다.

- ColPali 등 페이지 비전 검색이 필요할 때
- 렌더해야만 의미가 있는 다이어그램
- 배포본이 이미 PDF뿐일 때 (그때는 `01-pdf.md`)

둘 다 돌리면 비용만 는다. 차트 많은 월보에만 비전 보조 인덱스를 붙인다.

## 흔한 실패

- 전 슬라이드를 한 청크로 붙여 품번·대책이 교차한다.
- 노트를 버려 화면에 없는 근본원인이 인덱스에 없다.
- 차트 이미지를 스킵해 Pareto 숫자가 없다.
- bar/pie/line을 VLM 한 줄로만 남겨 표 질문이 실패한다.
- 공정 사진을 차트 추출에 넣어 빈 표가 생긴다.
- 슬라이드 표를 불릿 문장으로 바꿔 열 관계가 깨진다.
- 확장자만 보고 `.ppt` 바이너리를 python-pptx에 넣는다.

## 하지 말 것

- `.pptx → PDF → StandardPdfPipeline`을 기본으로 쓰기
- 마크다운 dump 후 토큰 윈도우로 자르기
- 빈 장·목차 장·백지 장을 본문과 같이 임베딩
- 원본을 지우고 추출 텍스트만 남기기
- MCP를 `search` 하나로 끝내기
- 모든 그림을 VLM으로만, 또는 모든 그림을 chart extraction으로만 보내기

## 인접 포맷

- `.ppt` → [08-ppt.md](08-ppt.md). LibreOffice 정규화 후 이 문서로 온다.
- `.pptm` → [28-pptm.md](28-pptm.md). 매크로 제거 후 이 문서.
- `.odp` → [26-odp.md](26-odp.md). Docling ODP가 우선. 약하면 변환 후 여기.
- 배포 PDF 덱 → [01-pdf.md](01-pdf.md). 슬라이드 경계가 페이지다.
- 서술 보고서 `.docx` → [02-docx.md](02-docx.md). 가족 A. 슬라이드 단위가 아니다.
