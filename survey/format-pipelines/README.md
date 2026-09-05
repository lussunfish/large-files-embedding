# 업무 문서 포맷 파이프라인 (40종)

시장품질 RAG/MCP 기준으로, 업무에서 자주 만나는 문서 포맷의 권장 입고 경로를 정리한다. 1–20은 기본 포맷, 21–40은 매크로·ODF·한컴·도면·DB·아카이브 등 파생 확장자다. 확장자가 아니라 **내용의 성격**(서술 / 정형 / 슬라이드 / 이미지 / 컨테이너 / 도면)으로 파이프라인을 고른다.

2026-09-05 웹 검색으로 각 포맷 파이프라인을 재검토했다. 요약은 [REVIEW.md](REVIEW.md)다.

상위 설계는 저장소 루트의 기존 문서를 따른다.

- `../market-quality-rag-improvement.md`
- `../excel-to-sql-decision.md`
- `../xlsx-20-samples-layer1.md`
- `../doc-format-handling.md`
- `../docx-pipeline.md`

## 공통 원칙

1. 확장자만 믿지 말고 시그니처로 재분류한다.
2. 서술 문서는 Docling JSON을 남기고, 마크다운 dump 후 토큰 자르기를 하지 않는다.
3. 엑셀·CSV 같은 정형 데이터는 Milvus에 넣지 않는다. Parquet 1층 → SQL 2층.
4. 레거시 오피스(`.doc` `.xls` `.ppt`)는 LibreOffice로 현대 포맷으로 정규화한 뒤 해당 파이프라인을 탄다.
5. 컨테이너(메일, 압축)는 먼저 풀고, 안의 파일을 다시 이 표로 보낸다.
6. MCP는 `search` 하나가 아니라 포맷 성격에 맞는 도구를 준다.

## 파이프라인 가족

| 가족 | 대상 | 한 줄 |
|---|---|---|
| A. 서술 Word형 | docx, odt, docm, (변환 후) doc/rtf/hwp/hwpx | SimplePipeline JSON → HybridChunker → Milvus |
| B. PDF형 | pdf, (스캔) tiff | StandardPdfPipeline 또는 OCR/비전 분기 |
| C. 정형 표 | xlsx, xlsm, xlsb, xls, csv, tsv, ods, parquet, accdb, mdb, cell, (표형) json/xml/yaml | 스트리밍 추출 → Parquet → SQL. RAG 금지. 매크로는 실행하지 않음 |
| D. 슬라이드 | pptx, pptm, ppt, odp, show | 슬라이드 단위 청크 + 노트 + 차트 캡션 |
| E. 가벼운 텍스트 | md, html, txt, (문서형) yaml | 헤더/문단 분할. 무거운 PDF 파이프라인 금지 |
| F. 이미지 | png/jpeg, tiff | OCR + VLM 캡션. 문서 스캔이면 B로 승격 |
| G. 컨테이너 | msg, eml, zip, mht | 본문/엔트리 분리 후 재분류 |
| H. 도면·다이어그램 | vsdx, vsd, dwg, dxf | 도형 텍스트 + 렌더 이미지. 바이너리 임베딩 금지 |

## 20종 목록

| # | 포맷 | 가족 | 권장 한 줄 | 문서 |
|---|---|---|---|---|
| 1 | PDF | B | 텍스트 층 있으면 StandardPdfPipeline, 스캔이면 OCR/비전 | [01-pdf.md](01-pdf.md) |
| 2 | DOCX | A | SimplePipeline JSON + HybridChunker. PDF로 바꾸지 말 것 | [02-docx.md](02-docx.md) |
| 3 | DOC | A | LibreOffice → DOCX 후 02와 동일 | [03-doc.md](03-doc.md) |
| 4 | XLSX | C | 스트리밍 → Parquet 1층 → 표준 팩트 SQL | [04-xlsx.md](04-xlsx.md) |
| 5 | XLS | C | calamine/polars 직접 읽기. LibreOffice는 폴백 | [05-xls.md](05-xls.md) |
| 6 | CSV | C | 인코딩 감지 후 바로 Parquet/SQL | [06-csv.md](06-csv.md) |
| 7 | PPTX | D | 슬라이드 1장 = 청크 1개. 노트·차트 분리 | [07-pptx.md](07-pptx.md) |
| 8 | PPT | D | LibreOffice → PPTX 후 07과 동일 | [08-ppt.md](08-ppt.md) |
| 9 | HWP | A | 한컴 또는 hwpkit/syhwp. Docling 미지원 | [09-hwp.md](09-hwp.md) |
| 10 | HWPX | A | ZIP/XML 또는 변환 후 DOCX 파이프라인 | [10-hwpx.md](10-hwpx.md) |
| 11 | MSG | G | Docling으로 본문, 첨부는 포맷별 재분기 | [11-msg.md](11-msg.md) |
| 12 | EML | G | MSG와 동일. MIME + 첨부 fan-out | [12-eml.md](12-eml.md) |
| 13 | HTML | E | 본문 추출 후 헤딩 분할. 브라우저 렌더 금지가 기본 | [13-html.md](13-html.md) |
| 14 | MD | E | ATX 헤더 기준 분할. Docling 불필요 | [14-md.md](14-md.md) |
| 15 | TXT | E | 인코딩 감지 + 문단 분할 | [15-txt.md](15-txt.md) |
| 16 | RTF | A | LibreOffice → DOCX 후 02와 동일 | [16-rtf.md](16-rtf.md) |
| 17 | PNG/JPEG | F | Docling 이미지 OCR(한글 RapidOCR). 차트는 VLM | [17-png-jpeg.md](17-png-jpeg.md) |
| 18 | TIFF | F/B | Docling TIFF/페이지 분리 + 한글 OCR | [18-tiff.md](18-tiff.md) |
| 19 | XML | C/A | 스키마 있으면 정형, 문서형이면 트리→섹션 | [19-xml.md](19-xml.md) |
| 20 | JSON | C/A | 배열/테이블이면 SQL, 문서형이면 경로 유지 텍스트 | [20-json.md](20-json.md) |

## 추가 20종 목록 (21–40)

| # | 포맷 | 가족 | 권장 한 줄 | 문서 |
|---|---|---|---|---|
| 21 | XLSM | C | 값만 추출해 04와 동일. 매크로는 실행·인덱싱하지 않음 | [21-xlsm.md](21-xlsm.md) |
| 22 | XLSB | C | calamine/fastexcel 직접. 병합 셀이면 LibreOffice | [22-xlsb.md](22-xlsb.md) |
| 23 | TSV | C | 구분자 `\t`인 CSV. 06과 동일 | [23-tsv.md](23-tsv.md) |
| 24 | ODS | C | calamine/polars scan. Docling ODS는 문서용 | [24-ods.md](24-ods.md) |
| 25 | ODT | A | Docling OdtDocumentBackend(odfdo) 우선 | [25-odt.md](25-odt.md) |
| 26 | ODP | D | Docling OdpDocumentBackend 우선. 슬라이드=청크 | [26-odp.md](26-odp.md) |
| 27 | DOCM | A | 매크로 Word. VBA는 버리고 본문만 02 | [27-docm.md](27-docm.md) |
| 28 | PPTM | D | 매크로 슬라이드. VBA는 버리고 07 | [28-pptm.md](28-pptm.md) |
| 29 | MHT | G | MIME 웹보관. HTML 추출 후 13 | [29-mht.md](29-mht.md) |
| 30 | ZIP | G | 엔트리 검사 후 내부 포맷으로 재귀 | [30-zip.md](30-zip.md) |
| 31 | ACCDB | C | Access → SQL 덤프. 행 임베딩 금지 | [31-accdb.md](31-accdb.md) |
| 32 | MDB | C | Jet Access. 변환/내보내기 후 31과 동일 | [32-mdb.md](32-mdb.md) |
| 33 | VSDX | H | Visio XML. 셰이프 텍스트 + 렌더 이미지 | [33-vsdx.md](33-vsdx.md) |
| 34 | VSD | H | 레거시 Visio. 변환 후 33 | [34-vsd.md](34-vsd.md) |
| 35 | DWG | H | ezdwg 또는 ODA→DXF→ezdxf. 플롯+속성 텍스트 | [35-dwg.md](35-dwg.md) |
| 36 | DXF | H | CAD 교환. 레이어·TEXT 엔티티 추출 | [36-dxf.md](36-dxf.md) |
| 37 | CELL | C | 한셀. 한컴/변환 후 xlsx 경로 | [37-cell.md](37-cell.md) |
| 38 | SHOW | D | 한쇼. 한컴/변환 후 pptx 경로 | [38-show.md](38-show.md) |
| 39 | YAML | C/E | 레코드면 SQL, 설정/문서면 경로 유지 텍스트 | [39-yaml.md](39-yaml.md) |
| 40 | PARQUET | C | 이미 컬럼형. DuckDB로 조회. 재임베딩 금지 | [40-parquet.md](40-parquet.md) |

## 입고 분기 (의사코드)

```
file
  → magic/시그니처
  → zip/메일/ole 컨테이너면 unwrap
  → switch
       pdf        → 텍스트 층 비율로 digital vs scan
       docx/odt              → 가족 A (odt는 Docling odfdo)
       doc/rtf               → LibreOffice → A (timeout·UserInstallation)
       hwp/hwpx              → 한컴 또는 hwpkit/syhwp → A 또는 B
       xlsx/xlsm/csv/tsv/parquet → 가족 C (calamine, xlsm 매크로 미실행)
       xls/xlsb/ods          → calamine 직접 → C (LO는 폴백)
       cell                  → 한컴 변환 후 C
       accdb/mdb             → mdbtools/SQL 덤프 → C
       pptx/pptm             → 가족 D
       odp                   → Docling odfdo → D
       ppt/show              → 변환 후 D
       html/md/txt           → 가족 E
       png/jpeg/tiff         → Docling 이미지 OCR; 텍스트 없으면 VLM
       xml/json/yaml         → 스키마 보고 C 또는 A/E
       msg/eml               → 본문 Docling + 첨부 재귀
       zip/mht               → unwrap 후 재귀
       vsdx                  → vsdx 라이브러리 셰이프 텍스트 + 렌더
       vsd/dwg/dxf           → 가족 H
       docm                  → 매크로 제거 후 A
```

## 작성 규칙

각 포맷 문서는 같은 목차를 따른다.

1. 결론 (선택 표 + 권장 한 줄)
2. 권장 파이프라인
3. 단계별 권장
4. 흔한 실패
5. 하지 말 것
6. 인접 포맷
