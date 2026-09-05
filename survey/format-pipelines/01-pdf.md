# PDF 권장 파이프라인

- 배경: 시장품질 RAG/MCP에서 PDF(가족 B)를 어떻게 넣을 것인가. 약 3,100건, 최대 100MB.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

디지털 PDF는 마크다운으로 먼저 보내지 않는다. Docling `StandardPdfPipeline`(layout + TableFormer)으로 JSON을 남기고, 제목 경로와 표를 분리해 임베딩한다. 텍스트 층이 빈약하면 RapidOCR(PP-OCR korean) 분기로 보낸다. 막대·원·선 차트는 `--enrich-chart-extraction`으로 숫자를 뽑는다. 도장·스캔·난해 페이지만 `VlmPipeline`+`granite_docling`을 선택으로 켠다. PDF를 DOCX로 바꾸는 것은 기본이 아니다.

권장 한 줄:

```
.pdf → 시그니처(%PDF) → 텍스트 층 밀도
     → 디지털: StandardPdfPipeline JSON (+ 차트 추출)
     → 스캔/희소: RapidOCR(PP-OCR korean)
     → 난해 페이지(선택): VlmPipeline + granite_docling
     → HybridChunker(contextualize + 표 CSV) → Milvus
     → MCP: outline / section / table / page
```

| 선택 | 판단 |
|---|---|
| 마크다운 dump 후 토큰 자르기 | 하지 말 것 |
| PDF → DOCX 변환 후 파싱 | 기본 경로 아님. 구조가 깨짐 |
| pdftotext만으로 본문 추출 | 표·계층 손실 |
| StandardPdfPipeline JSON + HybridChunker | **디지털 PDF 기본** |
| RapidOCR `lang=["korean"]` (PP-OCR v4/v5) | **스캔·혼합 OCR 기본** |
| `--enrich-chart-extraction` (bar/pie/line) | **Pareto·추세 차트 기본** |
| VlmPipeline + granite_docling | 선택. 도장·스캔·난해 페이지 |
| ColPali로 디지털 텍스트 대체 | 하지 말 것. 보조 인덱스 |
| 100MB를 통째로 메모리 적재 | 하지 말 것. 페이지 스트림 |

## 권장 파이프라인

```
업로드 .pdf
  1. 포맷 검증
       %PDF- 아니면 재분류. 암호·깨진 xref는 failed_pdf
  2. 텍스트 층 밀도
       앞·중간·끝 페이지 표본. 디지털 / 스캔 / 혼합
  3. 파싱
       디지털: StandardPdfPipeline (layout + TableFormer)
       차트: --enrich-chart-extraction / do_chart_extraction
       스캔·희소: RapidOCR lang=["korean"] (PP-OCR)
       난해 페이지(선택): VlmPipeline + granite_docling
       혼합: 페이지 단위 분기
       DoclingDocument JSON 저장
  4. 구조 분해
       목차 / 본문 / 표 / 그림·차트표 / 헤더·푸터 메타
  5. 청크
       HybridChunker + chunker.contextualize(chunk)
       표는 CSV 별도 청크, repeat_table_header=True
  6. 메타데이터
       제품, 차종, 품번, 문서유형, 기간, 페이지
  7. 인덱싱
       본문·표 → Milvus (하이브리드 + 필터)
       차트 많은 문서만 페이지 이미지 인덱스
  8. MCP
       get_outline, get_section, get_table, get_page, search_passages
```

원본 PDF와 JSON을 둘 다 보관한다. OCR·레이아웃·차트 추출 결과는 파생물이다. `parser=docling`, `pipeline=standard_pdf|ocr|vlm`, `ocr_engine`, `chart_extraction`을 메타에 남긴다.

## 단계별 권장

### 1. 입고: 시그니처와 텍스트 층

확장자만 믿지 않는다. 매직은 `%PDF-`다. 암호화·손상 파일은 배치를 멈추지 말고 실패로 남긴다.

텍스트 층은 전 페이지가 아니라 표본이면 된다. 추출 문자 수가 거의 없으면 스캔이다. 일부 페이지만 이미지인 혼합본은 페이지 단위로 가른다. 전체를 한 경로에 넣지 않는다.

### 2. 파싱: JSON을 남긴다

`StandardPdfPipeline`이 레이아웃과 TableFormer를 돌린다. 인덱싱 원본은 `DoclingDocument` JSON이다. 마크다운은 디버그용이다.

스캔·희소 페이지 OCR은 RapidOCR이 기본이다. `RapidOcrOptions(lang=["korean"])`로 PP-OCR 한글 인식기를 고른다. korean은 PP-OCR v4/v5에 있고, v6는 별칭만 있고 실제 한글 모델이 없다. 기본 lang(`chinese`)으로 돌리면 한글 스캔이 깨진다. EasyOCR `ko`는 보조다.

100MB는 파일 단위로 올리지 않는다. 페이지 스트림으로 읽고 배치 JSON을 붙인다. GPU는 layout/TableFormer/차트 추출에만 쓴다.

도장·스탬프·손글씨·레이아웃이 깨진 페이지만 `VlmPipeline`+`granite_docling`을 선택으로 켠다. 디지털 본문 전체를 VLM으로 대체하지 않는다. CLI는 `--pipeline vlm --vlm-model granite_docling`.

### 3. 청크: HybridChunker + 제목 경로

고정 길이 윈도우는 버린다. 임베딩 입력은 `chunk.text`가 아니라 `chunker.contextualize(chunk)`다. 제목 경로가 여기에 붙는다.

```text
[문서] 2024년 OO 차종 시장품질 월보
[섹션] 3. 클레임 현황 > 3.2 고장모드
[페이지] 12
[본문] ...
```

표는 `text`와 분리한다. 길면 행 그룹으로 자르고 `repeat_table_header=True`로 헤더를 각 조각에 반복한다.

### 4. 헤더·푸터·품번

머리글·바닥글에 품번·문서번호가 자주 있다. 본문 청크에 넣으면 모든 페이지에 반복되어 검색이 오염된다. 반복 헤더/푸터는 메타로 빼고 본문에서는 제거한다.

### 5. 차트·Pareto

그림 속 숫자는 TableFormer가 못 읽는다. 시장품질 월보의 Pareto·추세(막대·원·선)는 Docling 차트 추출을 켠다.

- CLI: `--enrich-chart-extraction`
- Python: `PdfPipelineOptions.do_chart_extraction = True`
- 결과는 `PictureItem.meta.tabular_chart.chart_data` (표 그리드)

추출된 차트 표는 일반 `TableItem`과 같이 `table` 청크로 둔다. 캡션·페이지·그림 인덱스를 메타에 붙인다. 저해상도·장식 차트·다중 시리즈가 섞이면 값이 틀릴 수 있어, 숫자 파싱·범위 검증을 한 겹 둔다. 차트 비중이 큰 문서만 ColPali/페이지 이미지 인덱스를 보조로 단다. 디지털 PDF의 텍스트 인덱스를 대체하지 않는다.

### 6. MCP

Codex CLI MCP는 `search` 하나가 아니다.

1. `get_outline(doc_id)` — 페이지·제목 트리
2. `get_section(doc_id, heading_path)` — 답변 근거
3. `get_table(doc_id, table_id)`
4. `get_page(doc_id, page)` — 차트·스캔 확인
5. `search_passages(query, filters)` — 하이브리드 + rerank

인용은 `파일명 + 페이지 + 섹션 경로`다. 3,100건을 필터 없이 의미 검색만 하면 다른 차종 월보가 올라온다.

## 흔한 실패

- 스캔 PDF를 디지털로 넣어 빈 청크가 쌓인다
- RapidOCR 기본 lang이 chinese라 한글 스캔이 깨진다
- 100MB를 한 번에 로드해 타임아웃·OOM이 난다
- 헤더 품번이 모든 청크에 반복되어 다른 이슈가 검색된다
- 표를 마크다운으로 평탄화해 병합 셀이 틀린다
- Pareto 숫자를 캡션만 믿고 차트 추출을 건너뛴다
- PDF→DOCX 변환으로 제목 계층이 사라진다
- 혼합본 전체를 OCR 또는 전체 텍스트로 단일 처리한다
- 디지털 PDF 전체에 VlmPipeline을 걸어 비용만 는다

## 하지 말 것

- 마크다운 dump + 토큰 청크를 기본으로 쓰는 것
- PDF를 DOCX로 바꿔 가족 A에 넣는 것
- 표 전체를 문장처럼 Milvus에 넣는 것
- 변환 실패·빈 페이지를 인덱싱하는 것
- ColPali만으로 디지털 본문을 대체하는 것
- 원본을 지우고 JSON만 남기는 것

## 인접 포맷

- 스캔 TIFF 멀티페이지는 페이지 분리 후 이 문서의 OCR 분기. `18-tiff.md`
- 이미지 한 장은 가족 F. `17-png-jpeg.md`
- Word는 PDF로 보내지 않는다. `02-docx.md`, `03-doc.md`
