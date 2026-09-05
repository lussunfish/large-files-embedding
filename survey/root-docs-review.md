# 루트 마크다운 검토 (2026-09-05)

대상은 워크스페이스 루트 5개다. `format-pipelines/` 하위는 별도 검토(`format-pipelines/REVIEW.md`)했다.

| 파일 | 판정 | 고친 점 |
|---|---|---|
| `market-quality-rag-improvement.md` | 아키텍처는 유효. 도구 문장이 구식 | 차트/엑셀/비전 retriever 갱신 |
| `excel-to-sql-decision.md` | 2층 설계는 유효 | 추출기를 calamine/polars로 명시 |
| `xlsx-20-samples-layer1.md` | 프로토콜은 유효 | Claude 30MB 공식 한도 확인, 프로파일러 엔진 |
| `doc-format-handling.md` | DOC 게이트는 유효. XLS 묶음은 틀림 | .xls를 LO 1순위에서 제외, #3819 |
| `docx-pipeline.md` | 거의 유효 | contextualize, 차트, LO 주의 |

## 파일별

### market-quality-rag-improvement.md

유지: 단일 Docling→Milvus가 실패하는 이유, 질문 4유형, MCP를 도구로 쪼개기, 골든셋 먼저, 하이브리드+rerank, 엑셀 SQL 분리, GraphRAG를 먼저 깔지 않기.

고침:

- “Docling이 그림 속 숫자를 거의 못 가져옴” → 기본 변환은 그렇다. 2026-02 Docling **chart understanding**(bar/pie/line → 표)을 켜면 달라진다.
- XLSX `openpyxl/DuckDB` → **calamine/polars → Parquet → SQL**.
- ColPali만 적힌 비전 검색 → **ColQwen2/2.5가 기본 후보** (ViDoRe·다국어). ColPali는 저비용 대안.
- contextual retrieval을 HybridChunker breadcrumb과 구분. Anthropic 수치는 여전히 인용 가능(실패 49%↓, rerank 67%↓)이나 3,100×100MB에 청크마다 전체 문서를 넣는 건 비싸다.

### excel-to-sql-decision.md

유지: MariaDB 1:1 적재 금지, Parquet 1층 + curated 2층, 스냅샷 메타, MCP list/describe/query, 서술 칸 RAG 복제.

고침: 다이어그램의 “openpyxl 전체 로드 금지”를 **calamine/polars 스트리밍**으로. Polars `read_excel` 기본 엔진이 calamine(fastexcel)이다. `.xls`/`.xlsb`도 같은 엔진.

MariaDB vs Postgres vs DuckDB 판단은 그대로 맞다.

### xlsx-20-samples-layer1.md

유지: 20개는 양식 표본, 프로필 JSON만 LLM에, 1층은 컬럼을 버리지 않음, TAG/스키마 정렬 용어.

고침: Claude 업로드 한도는 공식 문서 기준 **파일당 30MB, 채팅당 20개**(2026-09 Help Center). 비공식 500MB 설이 있으나 채팅 한도는 30MB로 둔다. 프로파일러는 calamine.

### doc-format-handling.md

유지: 시그니처 먼저, antiword 금지, 원본 보관, 한글 폰트, 변환 품질 체크 5항.

고침:

- “Docling이 .doc을 직접 못 읽는다”는 부정확. LibreOffice가 있으면 내부 변환한다. 그래도 **명시적 soffice**가 맞다 (#3819 hang/프로필 락).
- `.xls`를 `.doc`/`.ppt`와 같은 LO 게이트로 묶은 것은 **틀림**. calamine이 xls 값을 직접 읽는다.

### docx-pipeline.md

유지: SimplePipeline JSON, PDF로 바꾸지 않기, HybridChunker, 표 분리, parent-child, 헤더/푸터는 python-docx.

고침: `contextualize`, DrawingML 켤 때 timeout, 막대/원/선은 Docling 차트 추출.

## 웹 근거

- Docling formats / chart understanding / RapidOCR korean (2026-09 docs)
- Polars Excel calamine engine
- Anthropic Contextual Retrieval 원문 + 2026 해설 (49%/67%)
- ColQwen2.5 vs ColPali ViDoRe
- Claude Help Center 파일 30MB / 20 files
- Docling GitHub #3819 LibreOffice timeout/profile
