# 세션 대화 기록

- 워크스페이스: `large-files-embedding`
- 날짜: 2026-09-05
- 이 파일은 세션에서 오간 질문과 답변을 요약하지 않고 시간순으로 남긴다.
- 별도 md로 저장하라고 한 답변은 해당 경로를 가리키고, 본문은 그 파일에 있다.

---

## 사용자

회사 업무에 대해서 이야기 해보자. 나는 회사에서 ai 관련 프로젝트를 진행중이야. 최근에 하고 있는 일은 3000 여개의 우리 회사 제품의 시장품질 관련 문서들을 가지고 mcp 를 만들어서 codex cli 에 연동해서 인사이트를 담당자들(시장 품질 담당자) 에게 제공하는 서비스를 구현 중이야. 내가 지금까지 생성한 파이프라인은 파일 업로드(멀티 파일 가능) -> docling 을 이용한 문서 변환 -> milvus 에 벡터 저장 -> rag 를 이용한 mcp server 개발 -> codex cli 에 mcp 연동. 이렇게 구현을 했어. 그런데 서로 다른 확장자들(pdf, docx, xlsx, doc, md , pdf 등) 의 3100 여개의 최대 100mb 나 되는 파일들을 이 방식으로 처리하는데 정확도의 한계가 있다는 걸 느끼고 있어. 이런 상황에서 어떤 방식으로 개선을 할 수 있을 지 너의 도움이 필요해.

## 어시스턴트

정확도가 안 나오는 핵심 이유는, 3100개·최대 100MB·확장자 혼재 문서를 **하나의 Docling → 청크 → Milvus RAG**로 밀어 넣는 구조 자체에 있습니다. 시장품질 문서는 “비슷한 글”이 아니라 **서술 보고서 + 엑셀 수치 + 차트/표 + 품번·차종 코드**가 섞여 있어서, 텍스트 임베딩만으로는 담당자가 원하는 답을 자주 놓칩니다.

시장품질 담당자가 실제로 묻는 질문은 대략 네 종류입니다.

| 질문 유형 | 예 | 지금 파이프라인이 약한 이유 |
|---|---|---|
| 코드/키워드 조회 | 품번, 클레임번호, 차종 | 의미 검색은 약하고, 키워드/정확 매칭이 강해야 함 |
| 수치/집계 | 최근 3개월 클레임 건수, 불량률 | 엑셀을 문장으로 잘라 넣으면 행·열 관계가 깨짐 |
| 차트/표 해석 | Pareto, 월별 트렌드 그래프 | Docling이 그림 속 숫자를 거의 못 가져옴 |
| 원인·대책 서술 | 8D, 근본원인, 재발방지 | 섹션 문맥이 잘리면 대책이 다른 이슈와 섞임 |

실패는 보통 모델이 멍청해서가 아니라, **검색에 넣을 증거가 이미 깨져 있거나, 아예 인덱스에 없는** 경우가 많습니다.

1. **파싱 손실** — Docling은 PDF/DOCX 레이아웃에는 강하지만, 100MB급·스캔본·복잡한 표·엑셀 시트·차트 이미지에서는 정보가 잘리거나 평탄화됩니다. `.doc`는 `.docx`보다 더 취약합니다.
2. **청킹 손실** — 마크다운으로 보낸 뒤 고정 길이로 자르면 표가 반으로 갈라지고, 제목과 본문이 떨어지고, 100MB 문서 하나가 수천 청크가 됩니다.
3. **검색 손실** — 의미 벡터만 쓰면 품번은 거의 못 찾습니다. 메타데이터 필터가 없으면 3100건 전체가 매번 경쟁합니다.
4. **생성 손실** — MCP가 `search(query)` 하나면 Codex는 top-k 문장만 보고 답을 만듭니다.

목표 구조: “하나의 RAG”가 아니라 “질문 유형별 도구”.

```
문서 입고
  ├─ PDF/DOCX/MD  → 구조 파싱 → 계층 인덱스 + (선택) 페이지 이미지 인덱스
  ├─ XLSX         → 시트/스키마 추출 → DuckDB/SQL (벡터에 넣지 않음)
  └─ 이미지/차트  → 캡션 + 숫자 추출, 필요하면 페이지 비전 검색

MCP tools
  - list_documents(filters)
  - search_passages(query, filters)
  - get_outline / get_section
  - query_tables(...)
  - get_page_image(doc, page)
```

핵심: **엑셀은 RAG로 풀지 말고, 서술 문서는 RAG로, 차트는 비전으로** 나눕니다.

개선 순서:

1. 실패 분류 + 담당자 골든셋 20~50개 (retrieval / parse-table / generation)
2. 하이브리드 검색 + 메타데이터 + rerank. Docling HierarchicalChunker / HybridChunker, contextual retrieval
3. 엑셀을 벡터에서 분리 → DuckDB/SQL, 벡터에는 카탈로그만
4. 문서 계층 인덱스 (문서 요약 / 섹션 요약 / parent-child 청크)
5. 포맷별 파서 (Docling 단일 경로 폐기). 100MB는 페이지/시트 스트리밍
6. 차트·스캔이 많으면 ColPali/ColQwen 보조 인덱스

Codex MCP: `search` 하나만 두지 말 것. 파일명·페이지/시트·인용 강제. “모르겠다” 허용. 제품/기간 필터를 도구 인자로.

바로 하지 말 것: 임베딩만 교체, 전체 GraphRAG, 모든 PDF 비전 재인덱스, 청크 크기만 튜닝.

권장 실행: 2단계(하이브리드+메타+rerank)와 3단계(엑셀 분리)를 먼저.

후속 확인: (1) 문서를 못 찾는지 vs 표가 깨지는지 (2) xlsx / 스캔 PDF / 차트 보고서 비중 (3) 트렌드 집계 vs 이슈 원인 추적.

이 답변의 저장본: `survey/market-quality-rag-improvement.md` (이후 2026-09-05 재검토로 차트 추출·calamine·ColQwen 반영됨)

---

## 사용자

md 파일로 저장.

## 어시스턴트

저장했습니다. 경로: `market-quality-rag-improvement.md` (현재 `survey/market-quality-rag-improvement.md`)

---

## 사용자

xlsx 가 꽤 많은 편이고 , 사이즈도 100mb 정도 되는 것들도 있을 정도로 하나의 파일이 커. 이런 엑셀을 mariadb 같은 정형화 sql 로 db 화 하는 것이 좋을까?

## 어시스턴트

**정형 DB로 빼는 것은 맞고, 원본 엑셀을 MariaDB 테이블로 1:1 적재하는 것은 비추천입니다.** 숫자는 SQL, 설명은 RAG로 나누되, 100MB급 품질 엑셀은 **원본 보존 레이어**와 **분석용 스키마**를 분리해야 합니다.

| 선택 | 판단 |
|---|---|
| 엑셀을 Milvus에 넣는 것 | 하지 말 것 |
| 엑셀을 SQL로 조회 가능하게 만드는 것 | 해야 함 |
| 파일마다 MariaDB 테이블을 만드는 것 | 하지 말 것 |
| 클레임/불량 같은 공통 사실을 정규화해서 MariaDB에 넣는 것 | 목표가 맞음 |
| 바로 MariaDB만 구축 | 너무 이름. 먼저 Parquet 랜딩이 안전함 |

MariaDB가 나쁜 도구여서가 아닙니다. **엑셀 양식이 제각각인 상태에서 RDB에 바로 넣는 비용**이 문제입니다.

시장품질 엑셀은 대개 DB 테이블이 아니라 **사람이 보는 보고서**입니다. 헤더 위치, 병합 셀, 한 시트의 여러 표, 컬럼명 동의어, 100MB xlsx 메모리 폭주, 원장 vs 월보 스냅샷이 섞입니다.

바로 넣으면 (1) 파일/시트당 테이블 폭주 또는 (2) 억지 스키마로 의미 붕괴.

권하는 구조:

```
xlsx (최대 ~100MB)
  → 스트리밍 추출 (openpyxl 전체 로드 금지)
  → 1층: Parquet 랜딩 (파일/시트 원본, 스키마 그대로)
  → 2층: 표준 팩트 테이블 (MariaDB 또는 Postgres)
  → MCP: list_tables / describe_table / query_tables
  → 벡터에는 테이블·컬럼 설명만
```

MariaDB는 2층. 실험/매핑은 DuckDB + Parquet. 서비스화하면 MariaDB/Postgres.

100MB에서: calamine/Polars 스트리밍, BLOB 금지, 피벗/차트시트 스킵, 엑셀 시리얼 날짜, `source_file`/`report_period`/`ingested_at`.

MCP: 임의 SQL 금지, 읽기 전용 LIMIT, 서술 칸(원인/대책)은 RAG 복제.

실무 순서: 양식 3~5종 분류 → 질문 20개를 SQL로 쓸 수 있는지 → 최소 팩트 2~3개 → 파일 1개로 검증 → 그때 MariaDB. 3100개 전량 선적재 금지.

후속: 원장형 / 월보형 / 둘 다.

이 답변의 저장본: `survey/excel-to-sql-decision.md` (이후 calamine을 1순위 추출기로 명시하도록 수정됨)

---

## 사용자

save to md file

## 어시스턴트

저장했습니다. 경로: `excel-to-sql-decision.md` (현재 `survey/excel-to-sql-decision.md`)

---

## 사용자

유사한 형태의 xlsx 파일 20개를 너에게 준다면 ( 또는 다른 llm 에게 주고) 1층을 어떻게 정리하면 좋을지 요청하면 어느정도 처리를 해줄 수 있을까/ 전에 claude 에게 유사한 질의를 하니까 claude 는 대용량 파일들의 조합에서 유의미한 데이터를 찾아서 정리할 때는 청크 기반의 임베딩 방식보다는 다른 방식을 추천했었어. 그 용어를 까먹었지만.

## 어시스턴트

**20개면 1층 설계는 충분히 됩니다.** 다만 엑셀 원본을 모델 컨텍스트에 넣는 방식이 아니라, **파일은 코드가 읽고 LLM에는 얇은 프로필만 주는 방식**이어야 합니다. Claude가 청크 임베딩 대신 말한 것도 거의 이 계열입니다.

Claude가 말했을 법한 용어:

| 용어 | 의미 | 지금 과제와의 거리 |
|---|---|---|
| **Text-to-SQL / NL2SQL** | 질문 → SQL → 표에서 계산 | 2층·질의용. 1층 정리의 이름은 아님 |
| **TAG (Table-Augmented Generation)** | RAG의 표 버전. 검색이 아니라 테이블 쿼리로 근거를 가져옴 | 청크 RAG 대체로 가장 가까운 학술 이름 |
| **Code interpreter / 코드 실행 분석** | 엑셀을 프롬프트에 넣지 않고 Python/DuckDB가 읽고, 모델은 결과만 봄 | Claude가 실무에서 제일 자주 권하는 방식 |
| **Schema alignment / 스키마 정렬** | 비슷한 파일 20개의 컬럼을 하나의 표준 스키마로 맞춤 | **1층 정리의 본업** |
| **Medallion (Bronze–Silver–Gold)** | 원본 적재 → 정제 → 분석 테이블 | 1층/2층과 같음 |
| **Metadata-first** | 행 전체가 아니라 시트/컬럼 설명·샘플만 모델에 줌 | 100MB에서 필수 |

실무에서 제일 쓸모 있는 이름은 **스키마 정렬 + 코드 실행 프로필**, 질의 단계 이름은 **TAG / Text-to-SQL**.

20개는 데이터 전부가 아니라 **양식의 표본**입니다. 잘 되는 것: 패밀리 분류, 헤더 위치, 컬럼 동의어, 표준 컬럼, 변환 규칙, Parquet 스크립트, 실패 리포트. 잘 안 되는 것: 100MB를 채팅에 올리기, 담당자만 아는 컬럼 의미 확정, 시트 안 다중 표 100% 자동 분할.

성공률: 같은 템플릿 월보 70~90% / 양식 3~5종이면 패밀리 분류까지 / 레이아웃 제각각이면 분류만.

역할 분담:

```
20개 xlsx
  → (코드) 프로파일러가 파일마다 2~10KB JSON만 뽑음
  → (LLM) 패밀리 분류 + 표준 스키마 + 매핑 YAML
  → (코드) 20개 전부 Parquet 랜딩
  → (LLM) 실패 파일만 다시 봄
  → 담당자가 컬럼 의미 5~10개만 확인
```

1층은 컬럼을 거의 버리지 않음. 웹 Claude/ChatGPT 업로드는 용량 한도에 걸림. CLI + 프로파일러가 맞음.

이 답변의 저장본: `survey/xlsx-20-samples-layer1.md` (이후 Claude 공식 한도 파일당 30MB·채팅당 20개, 프로파일러 calamine으로 수정됨)

---

## 사용자

save to md

## 어시스턴트

저장했습니다. 경로: `xlsx-20-samples-layer1.md` (현재 `survey/xlsx-20-samples-layer1.md`)

---

## 사용자

doc 확장자는 어떻게 처리하는 게 좋을까?

## 어시스턴트

`.doc`는 `.docx`와 같은 Word가 아닙니다. 97–2003 바이너리(OLE)라서 python-docx/Docling이 직접 못 읽고, **LibreOffice로 `.docx`로 바꾼 뒤 기존 Word 파이프라인에 태우는 것**이 가장 무난합니다.

| 선택 | 판단 |
|---|---|
| `.doc`를 Docling/임베딩에 바로 넣기 | 하지 말 것 |
| `antiword` / `catdoc`으로 텍스트만 뽑기 | 하지 말 것 (표·한글 깨짐) |
| LibreOffice로 `.docx` 변환 후 Docling | **기본 경로** |
| 변환본만 남기고 원본 삭제 | 하지 말 것 |
| 엑셀처럼 SQL로 빼기 | 해당 없음 |

최신 Docling은 `.doc`를 지원한다고 적혀 있지만 내부도 LibreOffice 변환 → python-docx입니다. 입고에 변환을 명시하세요.

첫 단계는 시그니처 (`file` 명령). 가짜 docx/RTF가 흔합니다.

```bash
soffice --headless --norestore --nolockcheck \
  --convert-to docx:"MS Word 2007 XML" \
  --outdir /data/normalized \
  claim_8d.doc
```

한글 폰트 필수, soffice 동시성 약함, timeout, 실패는 `failed_doc`, 임베디드 엑셀 손실 검증.

구조가 중요하면 `.docx`, 도장/비전 검색이면 PDF. 기본은 `.doc → .docx → Docling JSON`.

업로드 직후 정규화 게이트. 원본 메타 `converted_from`, `converter=libreoffice`.

품질 확인: 성공률, 한글 깨짐, 표 개수, Heading, 임베디드 유실.

이 답변의 저장본: `survey/doc-format-handling.md` (이후 Docling 내장 변환 vs 명시적 soffice, #3819, `.xls`는 calamine 1순위로 수정됨)

---

## 사용자

save to md

## 어시스턴트

저장했습니다. 경로: `doc-format-handling.md` (현재 `survey/doc-format-handling.md`)

---

## 사용자

docx 확장자의 권장 파이프라인은?

## 어시스턴트

`.docx`는 엑셀처럼 SQL로 빼지 말고, PDF처럼 레이아웃 모델을 돌리지도 마세요. Word 스타일 트리를 살린 채 Docling JSON으로 읽고, 표만 따로 두는 경로가 맞습니다.

```
.docx → 시그니처 확인 → Docling SimplePipeline → JSON 원본 보관
      → HybridChunker(제목 경로 + 표 분리) → Milvus
      → MCP는 search가 아니라 outline / section / table
```

| 선택 | 판단 |
|---|---|
| 마크다운으로보낸 뒤 토큰 자르기 | 하지 말 것 |
| PDF로 변환 후 Docling PDF 파이프라인 | 기본 경로 아님 |
| python-docx만으로 텍스트 dump | 표·제목 계층이 약함 |
| Docling JSON + HybridChunker | **기본 경로** |
| 표를 본문 문장에 섞어 임베딩 | 하지 말 것 |
| xlsx처럼 MariaDB 적재 | 해당 없음 |

PDF용 `StandardPdfPipeline`은 `.docx`에 쓰지 않습니다. Word는 XML이라 **SimplePipeline**.

파이프라인: 포맷 검증 → SimplePipeline JSON → 목차/본문/표/그림 분해 → HybridChunker + breadcrumb, 표는 CSV 별도·헤더 반복 → 메타 → Milvus 하이브리드 → MCP list/outline/section/table/search.

Heading 스타일이 핵심. 굵은 글씨만 제목이면 통짜 본문. LibreOffice는 DrawingML일 때만.

표는 TableItem → CSV, 반복 양식이면 나중에 SQL 승격. 그림은 VLM. 헤더/푸터 품번은 python-docx. 인용은 파일명+섹션 경로.

PDF로 바꾸지 않는 이유: Heading을 픽셀로 다시 추정하게 됨.

표본 20개: Heading, 표, 헤더/푸터, 임베디드 엑셀, 이미지.

`.doc`는 LibreOffice 후 이 파이프라인과 동일.

이 답변의 저장본: `survey/docx-pipeline.md` (이후 `contextualize`, 차트 추출, soffice timeout 보강됨)

---

## 사용자

save to md

## 어시스턴트

저장했습니다. 경로: `docx-pipeline.md` (현재 `survey/docx-pipeline.md`)

---

## 사용자

업무에 자주 사용되는 대표적인 문서 포멧 20개를 리스트업 하고 , 이들은 각각 어떤 파이프라인을 타면 좋을지 를 분석해서 각각의 md 파일로 생성해줘. 적절한 폴더를 만들어서 거기에 모두 담아줘. 멀티에이전트 활용 가능;

## 어시스턴트

`format-pipelines/` 아래에 업무 포맷 20종의 권장 파이프라인을 나눠 저장했습니다. 인덱스는 `README.md`.

공통 원칙: 확장자가 아니라 성격으로 가름. 서술=Docling JSON, 표=Parquet/SQL, 레거시 오피스=LibreOffice 정규화.

| # | 포맷 | 권장 경로 | 파일 |
|---|---|---|---|
| 1 | PDF | 디지털 StandardPdfPipeline, 스캔 OCR/비전 | `01-pdf.md` |
| 2 | DOCX | SimplePipeline JSON + HybridChunker | `02-docx.md` |
| 3 | DOC | LibreOffice → DOCX | `03-doc.md` |
| 4 | XLSX | 스트리밍 → Parquet → SQL. RAG 금지 | `04-xlsx.md` |
| 5 | XLS | LibreOffice → XLSX (이후 calamine 직접 읽기로 수정됨) | `05-xls.md` |
| 6 | CSV | 인코딩 감지 후 Parquet/SQL | `06-csv.md` |
| 7 | PPTX | 슬라이드 1장 = 청크 1개 | `07-pptx.md` |
| 8 | PPT | LibreOffice → PPTX | `08-ppt.md` |
| 9 | HWP | 한글 변환 → DOCX 또는 PDF | `09-hwp.md` |
| 10 | HWPX | ZIP/XML 또는 변환 후 DOCX | `10-hwpx.md` |
| 11 | MSG | 본문 RAG + 첨부 재분기 | `11-msg.md` |
| 12 | EML | MSG와 동일, MIME | `12-eml.md` |
| 13 | HTML | 본문 추출 후 헤딩 분할 | `13-html.md` |
| 14 | MD | ATX 헤더 분할. Docling 불필요 | `14-md.md` |
| 15 | TXT | 인코딩 + 문단 분할 | `15-txt.md` |
| 16 | RTF | LibreOffice → DOCX | `16-rtf.md` |
| 17 | PNG/JPEG | OCR + VLM. 스캔이면 PDF 경로 | `17-png-jpeg.md` |
| 18 | TIFF | 멀티페이지 분리 후 스캔 PDF | `18-tiff.md` |
| 19 | XML | 스키마 있으면 정형, 없으면 트리 | `19-xml.md` |
| 20 | JSON | 배열이면 SQL, 문서형이면 텍스트 | `20-json.md` |

각 파일 목차: 결론 표, 권장 한 줄, 파이프라인, 단계, 실패, 하지 말 것, 인접 포맷.

현재 위치: `survey/format-pipelines/`

---

## 사용자

추가 20개 확장자를 도출하고 동일하게 md 파일로 정리해줘.

## 어시스턴트

추가 20개(21–40)를 같은 폴더·목차로 넣었고 README를 갱신했습니다. 1–20과 겹치지 않게 매크로 오피스, ODF, 한컴, Access, 도면, 아카이브를 골랐습니다. 도면은 가족 **H**.

| # | 확장자 | 가족 | 권장 경로 | 파일 |
|---|---|---|---|---|
| 21 | XLSM | C | 값만 추출, 매크로 미실행 | `21-xlsm.md` |
| 22 | XLSB | C | pyxlsb/LibreOffice → 이후 calamine 1순위로 수정 | `22-xlsb.md` |
| 23 | TSV | C | 구분자 `\t`인 CSV | `23-tsv.md` |
| 24 | ODS | C | ODF 스프레드시트 → Parquet | `24-ods.md` |
| 25 | ODT | A | ODF 문서 → DOCX와 동일 | `25-odt.md` |
| 26 | ODP | D | 슬라이드 1장 = 청크 1개 | `26-odp.md` |
| 27 | DOCM | A | VBA 버리고 DOCX 경로 | `27-docm.md` |
| 28 | PPTM | D | VBA 버리고 PPTX 경로 | `28-pptm.md` |
| 29 | MHT | G | MIME에서 HTML 추출 | `29-mht.md` |
| 30 | ZIP | G | 엔트리 검사 후 재귀 입고 | `30-zip.md` |
| 31 | ACCDB | C | Access 테이블 → SQL | `31-accdb.md` |
| 32 | MDB | C | Jet Access → 31과 동일 | `32-mdb.md` |
| 33 | VSDX | H | 셰이프 텍스트 + 렌더 이미지 | `33-vsdx.md` |
| 34 | VSD | H | 변환 후 VSDX | `34-vsd.md` |
| 35 | DWG | H | 플롯 이미지 + 속성 텍스트 | `35-dwg.md` |
| 36 | DXF | H | TEXT/레이어 추출 | `36-dxf.md` |
| 37 | CELL | C | 한셀 → xlsx 경로 | `37-cell.md` |
| 38 | SHOW | D | 한쇼 → pptx 경로 | `38-show.md` |
| 39 | YAML | C/E | 레코드면 SQL, 문서면 텍스트 | `39-yaml.md` |
| 40 | PARQUET | C | DuckDB 조회, 재임베딩 금지 | `40-parquet.md` |

---

## 사용자

@format-pipelines 의 각 md 파일에 대한 파이프라인을 검토해줘; 최신 정보 및 더 나은 정보 검색을 위해 웹 검색 활용 해줘; 멀티에이전트 활용;

## 어시스턴트

40개 파이프라인을 2026-09 기준 공식 문서·라이브러리로 재검토했고, 틀린 1순위만 본문에 반영했습니다. 전체 요약은 `format-pipelines/REVIEW.md`입니다.

방향(서술=JSON RAG, 표=SQL, 컨테이너=unwrap)은 그대로입니다. 바뀐 것은 **무엇으로 먼저 읽느냐**입니다.

| 포맷 | 이전 | 이후 |
|---|---|---|
| XLS, XLSB, ODS | LibreOffice 변환 먼저 | **calamine/polars가 직접 읽음**. LO는 폴백 |
| ODT, ODP | docx/pptx로 변환 | **Docling odfdo 네이티브** |
| MSG, EML | Docling 금지 | **본문은 Docling email 백엔드**. 첨부는 fan-out |
| PNG/JPEG/TIFF | 커스텀 OCR/VLM만 | **Docling 이미지 + RapidOCR korean** |
| HWP | pyhwp 중심 폴백 | 한컴 → **hwpkit/syhwp** → HWPX → LO → pyhwp(AGPL 최후) |
| DWG | LibreDWG/ODA만 | **ezdwg** 또는 ODA→DXF→ezdxf |
| VSDX | ZIP XML | **`vsdx`로 셰이프 텍스트** |
| ACCDB | 모호한 파서 | mdbtools. `access_parser`는 대용량에서 메모리 폭주 |

유지: 엑셀 행 Milvus 금지, DOCX JSON+HybridChunker, 매크로 미실행, HWP/CELL/SHOW/Visio/CAD/Access는 Docling이 안 읽음, ZIP slip.

운영: Docling GitHub #3819 — LibreOffice timeout + 파일별 UserInstallation.

PDF 월보: `--enrich-chart-extraction`. README 입고 분기도 맞춤.

배치 메모 파일: `_review-narrative.md`, `_review-tabular.md`, `_review-slides-hangul.md`, `_review-email-image.md`, `_review-cad-db.md`.

근거: Docling supported formats, OCR engines, Polars Excel calamine, 한컴 HWP 추출 정리, ezdxf odafc / ezdwg, mdbtools.

---

## 사용자

@format-pipelines 폴더의 하위 md 파일 제외하고 나머지 이 워크스페이스의 루트에 있는 md 파일들에 대해서도 내용을 각각 검토해줘. 웹검색을 활용;

## 어시스턴트

루트 md 5개만 재검토했습니다. 아키텍처는 그대로 두고 2026-09 기준 틀린 도구 문장만 고쳤습니다. 상세는 `root-docs-review.md`(현재 `survey/root-docs-review.md`).

| 파일 | 판정 |
|---|---|
| `market-quality-rag-improvement.md` | 구조는 유효. 차트·xlsx·ColPali 문장이 구식 |
| `excel-to-sql-decision.md` | 2층 설계는 유효. 추출기를 calamine으로 명시 |
| `xlsx-20-samples-layer1.md` | 프로필 JSON 프로토콜은 유효. Claude 30MB 한도 재확인 |
| `doc-format-handling.md` | `.doc` 게이트는 유효. `.xls`를 LO와 묶은 것은 틀림 |
| `docx-pipeline.md` | 거의 유효. contextualize·차트만 보강 |

고친 사실:

- 차트: 기본 변환은 그림 숫자를 못 가져옴. `--enrich-chart-extraction`으로 막대/원/선은 표.
- 엑셀: Polars `read_excel` 기본은 calamine/fastexcel. `.xls`/`.xlsb`도 직접 읽음.
- 비전: ColQwen2/2.5가 ColPali보다 다국어·작은 글씨에서 앞섬.
- contextual retrieval: Anthropic 49%/67%는 유효하나 3100×100MB에 청크마다 전체 문서는 비쌈. 1차는 HybridChunker 제목 경로.
- Claude 업로드: 공식 Help Center 파일당 30MB, 채팅당 20개.
- `.doc`: Docling이 LO만 있으면 받음. soffice는 숨기지 말 것 (#3819).
- `.xls`: `.doc`/`.ppt`와 같은 LibreOffice 게이트가 아님.

골든셋 → 하이브리드 검색 → 엑셀 SQL 분리 순서는 그대로.

---

## 사용자

survey 폴더를 만들고 나머지 파일 & 폴더를 어기 하위로 옮겨줘.

## 어시스턴트

`survey/`를 만들고 루트에 있던 파일과 폴더를 모두 그 아래로 옮겼습니다.

```
survey/
  market-quality-rag-improvement.md
  excel-to-sql-decision.md
  xlsx-20-samples-layer1.md
  doc-format-handling.md
  docx-pipeline.md
  root-docs-review.md
  format-pipelines/
```

문서끼리의 상대 경로는 같이 옮겨서 그대로 동작합니다.

---

## 사용자

@survey/format-pipelines 의 01 ~ 08 번까지의 파일타입에 대해 검토해보자. 이 파일들을 모두 처리할 수 있는 임베딩 파이프라인을 만든다면, 그리고 이를 이용해서 mcp server 를 만들어서 codex cli 에 연동하는 것을 목적으로 한다면, 어떤 서비스들이 로컬에 설치되어 있어야 하고 , 어떤 것들이 구현되어야 할까? 조사해줘.

## 어시스턴트

01–08을 한 파이프라인으로 묶으면 **임베딩만으로 끝나지 않습니다.** PDF·Word·PPT는 벡터, 엑셀·CSV는 SQL이고, MCP가 둘을 Codex에 하나의 도구 세트로 보여 줘야 합니다.

대상 포맷:

| # | 포맷 | 가족 | 실제 처리 |
|---|---|---|---|
| 01 | PDF | B | Docling JSON → HybridChunker → Milvus |
| 02 | DOCX | A | SimplePipeline → 동일 |
| 03 | DOC | A | LibreOffice → DOCX → 02 |
| 04 | XLSX | C | calamine → Parquet → DuckDB/SQL. **행 임베딩 금지** |
| 05 | XLS | C | calamine 직접. 실패만 LibreOffice |
| 06 | CSV | C | polars `scan_csv` → Parquet/SQL |
| 07 | PPTX | D | 슬라이드 1장 = 청크 1개 → Milvus |
| 08 | PPT | D | LibreOffice → PPTX → 07 |

표(04–06)를 청크로 넣으면 “클레임 건수” 질문이 다시 깨집니다. 로컬 스택은 **입고 라우터 + 서술 인덱스 + 표 엔진 + MCP** 네 덩어리입니다.

### 1. 로컬에 설치할 것

필수:

| 구분 | 무엇 | 왜 |
|---|---|---|
| 런타임 | **Python 3.10+** (3.12 권장) | Docling 2.70+는 3.10 미만 미지원 |
| OS 패키지 | **LibreOffice** (`soffice`) | `.doc`/`.ppt` 정규화. `.xls` 폴백. Docling 내부 변환도 이걸 부름 |
| 폰트 | **Noto CJK / Nanum** | headless 변환 시 한글 `□□` 방지 |
| Python | **`docling[rapidocr]`** | PDF 레이아웃·TableFormer, DOCX/PPTX, 스캔 OCR |
| Python | **`polars` + `fastexcel`(calamine)** | xlsx/xls 스트리밍. openpyxl 전체 로드 금지 |
| Python | **`duckdb` + `pyarrow`** | Parquet 1층 조회. MariaDB 전에 MCP SQL |
| Python | **`pymilvus`** (+ **Milvus Lite** 또는 서버) | 서술 청크 벡터 |
| Python | 임베딩 모델 런타임 | 로컬이면 `sentence-transformers` / FastEmbed, 아니면 OpenAI·SpaceXAI API |
| Python | **MCP SDK** (`mcp`) | Codex stdio 서버 |
| Python | **`python-magic` 또는 `filetype`** | 확장자 위조 판별 |
| Python | **`charset-normalizer`** | CSV cp949/utf-8-sig |

LibreOffice는 pip가 아닙니다. macOS면 `brew install --cask libreoffice` 또는 공식 패키지. `PATH`에 `soffice`. Docling은 `DOCLING_LIBREOFFICE_CMD`.

거의 필수: RapidOCR `lang=["korean"]` (기본 lang이 chinese면 한글 스캔 깨짐), Milvus sparse/BM25, reranker (`BAAI/bge-reranker-v2-m3`), 한글 임베딩 (`BAAI/bge-m3`).

선택: `docling[vlm]` + Granite-Docling, GPU/Apple Silicon, MariaDB, Docker+Milvus standalone, Ollama, JODConverter/soffice 워커 풀, ColQwen2.5.

Milvus Lite는 데몬 없이 파일 하나. 서비스화하면 `localhost:19530`.

### 2. 직접 구현할 것

A. 입고 워커 (배치 CLI)

```
file → magic/시그니처
  → .doc/.ppt → soffice (timeout, UserInstallation, 한글 폰트)
  → 가족 A/B/D → Docling JSON 저장 → HybridChunker → embed → Milvus
  → 가족 C     → calamine/scan_csv → Parquet → DuckDB
  → 실패는 failed/ 큐. 배치 중단 금지
```

모듈: 포맷 라우터, soffice 게이트(#3819), Docling 어댑터, 청커, 표 추출기, 메타 추출, 원본 스토어.

B. 두 저장소

- Milvus: `chunk_id`, dense, sparse, text, doc_id, path, family, section_path 또는 slide_index, page, chunk_type, 제품/기간 필터
- DuckDB: `sheets_raw` 1층, 이후 `claim_event` 2층. 카탈로그만 벡터에도

C. MCP 서버

서술: `list_documents`, `search_passages`, `get_outline`, `get_section`, `get_table`, `get_page`, `list_slides` / `get_slide`

표: `list_tables`, `describe_table`, `query_tables` (읽기 전용, LIMIT, 가능하면 filters+group_by)

공통: 파일명+페이지/시트/섹션, 도구 출력 토큰 상한, 근거 없음 허용.

입고는 MCP 밖에서. MCP는 조회만. 첫 도구 호출에 Docling 로드하면 Codex `startup_timeout_sec` 기본 10초를 넘김.

D. Codex 연동

`~/.codex/config.toml`:

```toml
[mcp_servers.market-quality]
command = "uv"
args = ["run", "python", "-m", "market_quality_mcp"]
cwd = "/path/to/project"
startup_timeout_sec = 30
tool_timeout_sec = 60
```

도구 description에 언제 어떤 도구를 쓸지 명시. 조회는 auto. `codex mcp add` 후 TUI `/mcp`.

E. 골든셋 20–50, 입고 로그, JSON에서 재임베딩.

### 3. 최소 로컬 vs 권장

노트북 데모: Python 3.12, LibreOffice+한글 폰트, `docling[rapidocr]`, polars, fastexcel, duckdb, pymilvus, mcp, sentence-transformers 또는 API. `originals/` `derived/` `milvus.db` `duckdb.db`.

파일럿: + reranker + BGE-M3, soffice 격리, DuckDB 유지, MCP 조회 전용.

1차에 넣지 말 것: ColQwen 전체, MariaDB 전량, GraphRAG, xlsx를 Docling으로 임베딩.

### 4. 구현 순서

1. 라우터 + soffice + 시그니처
2. DOCX/PPTX/디지털 PDF → JSON → HybridChunker → Milvus Lite
3. XLSX/XLS/CSV → Parquet → DuckDB
4. MCP 8–10개 + Codex config.toml
5. RapidOCR korean, 차트 추출, rerank
6. `.doc`/`.ppt` 대량, VLM, ColQwen

1–4면 Codex에서 “이 8D 대책”과 “이 차종 클레임 건수”를 도구를 나눠 물을 수 있습니다.

---

## 사용자

ㅇ 세션에서 나눈 대화 내용을 요약하지 말고 md 파일로 저장.  ← (직전 질문과 이어짐) 01–08 코어 후 09부터 확장자를 하나씩 추가해 전체 포맷 MCP를 구현하면 될까?

직전 사용자 질문 전문:

이걸 먼저 준비해 놓고 필요한 것들을 모두 구현한다면, 다음으로 @survey/format-pipelines 의 09 부터 확장자를 계속 하나씩 추가하는 방식으로 전체 파일포멧을 지원하는 임베딩 mcp-server 를 구현하면 될까?

## 어시스턴트

**됩니다.** 01–08을 코어로 굳히고 09부터 핸들러만 붙이는 방식이 맞습니다. 다만 목표를 “모든 확장자를 임베딩하는 MCP”로 두면 09부터 다시 막힙니다. 코어가 이미 **라우터 + (서술 벡터 | 표 SQL) + 조회 MCP**여야 이후 포맷이 플러그인처럼 들어갑니다.

### 되는 이유

01–08이 이미 네 가족의 대표입니다.

| 코어가 가진 것 | 이후가 재사용하는 것 |
|---|---|
| A: DOCX JSON + HybridChunker | HWP, HWPX, RTF, ODT, DOCM |
| B: PDF + OCR | TIFF, 스캔 PNG |
| C: calamine → Parquet → DuckDB | XLS, XLSM, XLSB, TSV, ODS, CELL, Access, YAML/JSON 표 |
| D: 슬라이드=청크 | PPT, PPTM, ODP, SHOW |
| soffice 게이트 | DOC, PPT, RTF, 일부 폴백 |
| MCP 조회 도구 | 포맷이 늘어도 도구 이름은 거의 그대로 |

09를 넣을 때 새로 짤 것은 **변환기 한 개**이지, Milvus 스키마나 Codex 연동이 아닙니다.

### 코어(01–08)에 반드시 심을 확장 지점

```
ingest(path)
  → detect(magic, ext)
  → handler.normalize()          # doc→docx, ppt→pptx, hwp→docx …
  → handler.extract()
        narrative → Docling JSON → chunks → Milvus
        tabular   → Parquet → DuckDB
        container → 자식 파일 목록 → ingest 재귀
  → catalog 기록 (doc_id, family, tools)
```

MCP는 포맷 이름이 아니라 **가족**을 봅니다.

- 서술: `search_passages` / `get_outline` / `get_section`
- 표: `query_tables`
- 슬라이드: `get_slide`
- (나중에 H) 도면: `get_page_image` / `search_shape_text`

09를 넣을 때마다 `search_hwp`를 만들면 도구가 폭발하고 Codex가 헷갈립니다.

입고는 MCP 밖에. HWP 변환을 첫 도구 호출에 넣으면 Codex 타임아웃.

### 09부터는 번호 순이 아니라 ‘종류’ 순

번호대로 가면 11 MSG에서 설계가 한 번 흔들립니다. 메일은 새 임베딩이 아니라 **컨테이너**입니다.

권장 추가 순서:

1. **변환만 하면 기존 파이프** — 16 RTF, 25 ODT, 26 ODP, 21–23 XLSM/XLSB/TSV, 24 ODS, 27–28 DOCM/PPTM
2. **한국 업무 본류** — 09 HWP, 10 HWPX, 37 CELL, 38 SHOW
3. **컨테이너 (재귀)** — 11 MSG, 12 EML, 29 MHT, 30 ZIP
4. **가벼운 텍스트** — 13 HTML, 14 MD, 15 TXT
5. **이미지** — 17 PNG/JPEG, 18 TIFF
6. **이중 분기** — 19 XML, 20 JSON, 39 YAML, 40 Parquet
7. **새 가족 H (마지막)** — 31–32 Access, 33–36 Visio/CAD

코퍼스에 HWP가 많으면 2를 1보다 앞당김. 순서는 파일 번호가 아니라 **실제 3,100건 비중**.

### “전체 포맷 임베딩 MCP”가 아닌 이유

- 04–06, 21–24, 31–32, 40은 **끝까지 SQL**
- 11–12, 29–30은 **풀어서 자식만** 기존 파이프
- 35–36은 **텍스트+플롯**. DWG 바이트 임베딩 금지

제품 이름은 임베딩 서버보다 **문서 인텔리전스 MCP**(서술 검색 + 표 질의). 임베딩은 A/B/D/E/F의 저장소일 뿐입니다.

### 09를 넣기 전에 코어가 통과해야 하는 테스트

1. 가짜 확장자: `.doc`인 docx, `.xls`인 xlsx
2. `.doc`/`.ppt` soffice timeout·한글 폰트
3. 100MB xlsx가 Milvus가 아니라 DuckDB에 들어감
4. Codex가 “대책”은 `get_section`, “건수”는 `query_tables`를 고름
5. 실패 파일이 배치를 안 죽임

그다음 09 HWP는 `normalize(): hwp → docx|md+tables`만 구현하고 02 파이프에 태우면 됩니다.

**결론:** 01–08을 먼저 구현하고 09부터 하나씩 추가하는 전략은 맞습니다. 코어에 라우터·두 저장소·가족별 MCP·컨테이너 재귀만 열어 두면, 40종은 “새 서버”가 아니라 **핸들러 목록**이 됩니다.

---

## 사용자

이 세션에서 나눈 대화 내용을 요약하지 말고 md 파일로 저장.

## 어시스턴트

이 파일 (`survey/session-conversation.md`)으로 저장함.

---

## 이 세션에서 만들어진 산출물 경로 (대화 후 이동 포함)

```
survey/
  session-conversation.md          ← 이 파일
  market-quality-rag-improvement.md
  excel-to-sql-decision.md
  xlsx-20-samples-layer1.md
  doc-format-handling.md
  docx-pipeline.md
  root-docs-review.md
  format-pipelines/
    README.md
    REVIEW.md
    01-pdf.md … 40-parquet.md
    _review-*.md
```

포맷별 파이프라인 본문(01–40)과 재검토 패치 전문은 각 파일에 있으며, 이 기록은 세션의 질의응답을 시간순으로 남긴다.
