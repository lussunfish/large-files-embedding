# 파이프라인 문서 갱신 메모 (2026-09)

대상은 `format-pipelines/` 지정 9개다. 전체 재작성 없이 오래된 주장만 고쳤다. Docling 공식 입력(2026-09): PDF, DOCX/XLSX/PPTX, DOC/XLS/PPT(LibreOffice), ODT/ODS/ODP(odfdo), MD, HTML, CSV, 이미지, EML/MSG, TXT, EPUB, Pages, ASR, XBRL. HWP·RTF는 없다.

## 파일별 변경

### `01-pdf.md`
- 차트 추출을 기본 보강으로 넣었다. CLI `--enrich-chart-extraction`, `PictureItem.meta.tabular_chart`. 막대·원·선(Pareto·추세).
- 스캔 OCR 기본을 RapidOCR `lang=["korean"]`(PP-OCR v4/v5)로 고정했다. v6는 한글 모델이 없다. EasyOCR은 보조.
- 도장·스캔·난해 페이지만 `VlmPipeline`+`granite_docling` 선택. 디지털 본문 전체 VLM은 금지.
- 페이지 스트림(100MB)은 유지. HybridChunker는 `contextualize` + `repeat_table_header=True`.

### `02-docx.md`
- HybridChunker 임베딩 입력을 `chunker.contextualize(chunk)`로 명시했다.
- `.doc` 인접 경로: Docling 내장 변환이 아니라 입고 soffice 게이트를 쓴다고 적었다.

### `03-doc.md`
- “Docling이 .doc을 직접 못 읽는다”를 고쳤다. 공식 입력이고 내부는 `convert_to_modern_format`(LibreOffice).
- 그래도 명시적 soffice 게이트가 기본이다. timeout·`UserInstallation` 격리.
- GitHub #3819 (2026-07): 내장 LibreOffice 호출도 hang·기본 프로필 충돌. 내장 변환을 써도 같다.

### `13-html.md`
- 내부 보고서는 Docling HTML 백엔드(`HTMLDocumentBackend`, bs4)가 공식 경로다.
- 웹 저장본의 크롬(내비/광고)은 여전히 readability/trafilatura가 먼저다.

### `14-md.md`
- “Docling 불필요”를 “기본은 헤딩 분할, Docling은 선택”으로 완화했다.
- Markdown 백엔드(marko)는 통합 JSON이 필요할 때만. PDF/Word 파이프라인은 그대로 금지.

### `15-txt.md`
- 기본은 인코딩 + 문단 분할. Docling 텍스트 백엔드는 통합 JSON용 선택.
- PDF 파이프라인에 txt를 넣는 금지는 유지.

### `16-rtf.md`
- LibreOffice → docx가 여전히 기본이다.
- Docling 공식 입력에 RTF가 없다. `.doc`용 `convert_to_modern_format` 경로도 없다.

### `25-odt.md`
- 네이티브 `OdtDocumentBackend`(odfdo) + SimplePipeline이 1순위다.
- LibreOffice convert-to-docx는 폴백만. 기본 입고에서 docx 변환을 요구하지 않는다.

### `27-docm.md`
- 매크로 제거 후 docx 파싱은 유지.
- Docling은 ZIP/OOXML이면 확장자와 무관하게 docx 백엔드로 읽는다. VBA는 먼저 뺀다.

## 공통으로 맞춘 점
- HybridChunker 유지. `repeat_table_header=True`. 임베딩은 `chunker.contextualize(chunk)`.
- 하다/다 체, 기존 절 구조는 유지했다.
