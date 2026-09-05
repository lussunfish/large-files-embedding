# 포맷 파이프라인 검토 (2026-09-05)

40개 포맷 문서를 Docling 공식 지원 목록, Polars/calamine, 한글 오픈소스, CAD/Visio/Access 도구 기준으로 재검토하고 본문을 고쳤다. 방향(서술=JSON RAG, 표=SQL, 컨테이너=unwrap)은 유지했다. 바뀐 것은 **1순위 도구**다.

근거: [Docling supported formats](https://docling-project.github.io/docling/usage/supported_formats/), [OCR engines](https://docling-project.github.io/docling/concepts/OCR/), [Polars Excel](https://docs.pola.rs/user-guide/io/excel/), [calamine](https://github.com/tafia/calamine), [한컴 HWP 추출 정리](https://blog.hancom.com/en/hwp-hwpx-data-extraction-format-library/), ezdxf odafc / ezdwg, mdbtools.

배치 메모: `_review-narrative.md`, `_review-tabular.md`, `_review-slides-hangul.md`, `_review-email-image.md`, `_review-cad-db.md`.

## 뒤집은 권고 (중요)

| 포맷 | 이전 | 이후 | 이유 |
|---|---|---|---|
| XLS / XLSB / ODS | LibreOffice 변환이 1순위 | **calamine/polars 직접 읽기** | fastexcel/calamine이 xls·xlsx·xlsm·xlsb·ods를 읽음. xlsb는 병합 셀 미지원이라 그때만 LO |
| XLSM | 값 추출은 맞음 | calamine이 값을 읽고 VBA는 무시 | 매크로 실행 금지는 유지 |
| ODT / ODP | 변환 후 docx/pptx | **Docling odfdo 네이티브** | 2026 Docling What's new: ODF 지원 |
| MSG / EML | Docling 투입 금지 | **본문은 Docling email 백엔드 허용**, 첨부는 여전히 fan-out | 공식 입력이 EML/MSG. `list_attachments`는 이름만 |
| PNG/JPEG/TIFF | 커스텀 OCR/VLM만 | **Docling 이미지 입력 + RapidOCR korean**이 스캔 기본. 차트는 VLM | Docling이 PNG/JPEG/TIFF/BMP/WEBP를 받음 |
| HWP | pyhwp 폴백 중심 | 한컴 → **hwpkit/syhwp** → HWPX → LO → pyhwp(AGPL 최후) | pyhwp는 2020 이후 정체, HWPX 없음 |
| DWG | LibreDWG/ODA만 | **ezdwg 또는 ODA→DXF→ezdxf** | ezdxf는 DWG를 직접 못 연다. ezdwg가 생김 |
| VSDX | ZIP XML 일반화 | **`vsdx` 라이브러리로 셰이프 텍스트** | dave-howard/vsdx |
| ACCDB | access_parser 가능처럼 읽힐 여지 | mdbtools + polars 래퍼. access_parser는 전체 메모리 로드라 대용량 금지 | pyaccdb는 암호 accdb |

## 유지한 권고 (맞음)

- 엑셀/CSV/Parquet 행을 Milvus에 넣지 않는다.
- DOCX는 SimplePipeline JSON + HybridChunker. PDF로 바꾸지 않는다.
- PDF는 텍스트 층으로 디지털/스캔 분기. 마크다운 dump 금지.
- `.doc`/`.ppt`/`.rtf`는 LibreOffice 정규화. RTF는 Docling 공식 입력이 아님.
- 매크로(xlsm/docm/pptm)는 실행하지 않는다.
- ZIP slip, 메일 첨부 재분기, CAD 바이너리 임베딩 금지.
- HWP/CELL/SHOW/VSD/DWG/Access는 Docling이 안 읽는다.

## 포맷별 한 줄 판정

**가족 A (서술)**  
01 PDF — 유효. 추가: `--enrich-chart-extraction`(bar/pie/line), RapidOCR `korean`, 난해 페이지 `VlmPipeline`.  
02 DOCX — 유효. `contextualize` + `repeat_table_header`.  
03 DOC — 유효. Docling도 LO로 변환하지만 **명시적 soffice + timeout + UserInstallation** (#3819 hang/프로필 충돌).  
09 HWP — 도구 순서 교체. Docling 미지원은 유지.  
10 HWPX — unzip + hwpkit/syhwp/jakal. Heading 필요 시 한컴 DOCX.  
13 HTML — 내부 보고서는 Docling HTML, 웹은 readability.  
14 MD / 15 TXT — 헤딩·문단 분할 기본. Docling은 통합 JSON이 필요할 때만.  
16 RTF — LO → docx. 변경 없음.  
25 ODT — Docling 1순위.  
27 DOCM — 매크로 제거 후 02.

**가족 C (정형)**  
04 XLSX — fastexcel/calamine 기본. openpyxl은 차트·정의된 이름. Docling XLSX는 100MB SQL에 쓰지 않음.  
05 XLS / 21 XLSM / 22 XLSB / 24 ODS — calamine 1순위.  
06 CSV / 23 TSV — `scan_csv`. Docling CSV가 있어도 행 임베딩 금지.  
31 ACCDB / 32 MDB — mdbtools (`mdb-json` 포함).  
37 CELL — 한컴 유지.  
39 YAML / 19 XML / 20 JSON — 이중 분기 유지. 범용 Docling XML/JSON 없음(XBRL/JATS 등만).  
40 PARQUET — DuckDB/polars scan. 유효.

**가족 D (슬라이드)**  
07 PPTX — 슬라이드=청크 유지. bar/pie/line은 Docling chart table, 공정 사진은 VLM.  
08 PPT / 28 PPTM — 변환·매크로 제거 후 07.  
26 ODP — Docling 1순위.  
38 SHOW — 한컴 유지.

**가족 F/G/H**  
11/12 메일 — 본문 Docling, 첨부 재귀.  
17/18 이미지 — Docling OCR 기본.  
29 MHT / 30 ZIP — 유효. Docling은 일반 zip을 문서로 안 받음(`.dclx` 제외).  
33 VSDX — `vsdx` 패키지.  
34 VSD — libvisio/LO 변환.  
35 DWG — ezdwg 또는 ODA+ezdxf.  
36 DXF — ezdxf + 대용량 `iterdxf`.

## 운영 공통 (Docling #3819)

LibreOffice를 Docling이 내부 호출하든, 우리가 직접 부르든 **timeout과 파일별 `UserInstallation`** 이 필요하다. 기본 프로필 락으로 동시 변환이 죽거나 차트가 빠진다.

## 아직 안 바꾼 것

- 청크 임베딩 모델 선정, rerank, Milvus 스키마.
- GraphRAG, ColPali를 기본 경로로 올리는 것 — 차트 PDF 보조 인덱스는 01에 선택으로만 둠.
- 한컴 `.cell`/`.show`의 공개 파서는 여전히 약하다. Windows 한컴이 없으면 품질이 떨어진다.
