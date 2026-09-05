# ODS 권장 파이프라인

- 배경: 시장품질 RAG/MCP에서 OpenDocument 스프레드시트(`.ods`, 가족 C)를 어떻게 넣을 것인가. ZIP+XML이다. 숫자는 SQL, 서술 청크가 아니다. 약 3,100건, 최대 ~100MB.
- 관련 문서: `../excel-to-sql-decision.md`, `../xlsx-20-samples-layer1.md`, `README.md`

## 결론

`.ods`는 엑셀이 아니지만 C 가족이다. **calamine/polars가 ODS를 직접 읽는다.** Docling `OdsDocumentBackend`(odfdo)는 시트를 문서로 볼 때만. SQL 경로에 Docling RAG를 쓰지 않는다. 압축을 풀어 XML 태그를 임베딩하지 않는다. 시트는 여러 장일 수 있다.

| 선택 | 판단 |
|---|---|
| ZIP을 풀어 `content.xml` 태그를 Milvus | 하지 말 것 |
| ODS를 서술 문서로 HybridChunker | 하지 말 것. RAG 아님 |
| fastexcel/calamine (polars) → Parquet 1층 → SQL | **기본 경로** |
| LibreOffice → xlsx 후 04 | 폴백. 변환·깨진 ODF |
| Docling OdsDocumentBackend (odfdo) | 시트를 문서로 볼 때만. SQL 경로 아님 |
| odfpy 직접 파싱 | 보조. 날짜·병합은 표본 검증 |
| 파일마다 SQL 테이블 | 하지 말 것 |
| 여러 시트를 한 표로 강제 UNION | 하지 말 것 |

권장 한 줄:

```
.ods → 시그니처(ZIP + mimetype=spreadsheet) → calamine/polars 직접 읽기
     → Parquet 1층 → SQL 2층. XML 태그 임베딩 금지. RAG 아님
     → 실패만 LibreOffice → xlsx. Docling ODS는 문서 경로
```

## 권장 파이프라인

```
업로드 .ods
  1. 시그니처
       ZIP + application/vnd.oasis.opendocument.spreadsheet → ODS
       ZIP + opendocument.text                               → 25-odt
       ZIP/OOXML (xl/)                                       → 04/21
       OLE                                                   → 05
  2. 시트 인벤토리
       여러 시트. 빈 시트·차트만 있는 시트는 메타만
  3. 값 추출
       우선: polars read_excel(engine=calamine) / python-calamine
       폴백: LibreOffice → xlsx 후 04
       Docling OdsDocumentBackend(odfdo)는 시트-as-문서일 때만
       XML DOM 전체 로드 금지
  4. 프로파일 JSON
       시트명, 행/열, 헤더, 타입, 샘플 5행
  5. Parquet 1층
       source_file, sheet_name, report_period, template_family
       원본 컬럼 유지
  6. SQL 2층 + MCP
       팩트만. list_tables / describe_table / query_tables
       벡터에는 카탈로그만. 행 금지
  원본 .ods 보관
```

Docling `OdsDocumentBackend`(odfdo)는 시트를 문서로 취급한다. 가족 C(SQL)에는 calamine/polars scan이 맞다. StandardPdfPipeline·마크다운 export는 쓰지 않는다.

## 단계별 권장

### 1. 컨테이너를 문서처럼 풀지 않는다

ODS는 ZIP이다. `mimetype`, `content.xml`, `styles.xml`이 있다. `content.xml`을 청크하면 `<table:table-cell>`이 본문이 된다. XXE· ent 전개도 XML과 같다. 외부 엔티티는 끈다.

시그니처가 `opendocument.text`면 스프레드시트가 아니다. [25-odt.md](25-odt.md)로 보낸다. 확장자만 `.ods`인 docx/xlsx도 있다.

### 2. 기본은 calamine, 변환은 폴백

python-calamine / Polars `read_excel`(기본 엔진 calamine)은 ODS를 직접 읽는다. pandas 3.1 `engine='calamine'`도 같다. 변환 없이 04와 같은 Parquet 1층으로 간다.

LibreOffice headless → xlsx는 calamine 실패·깨진 ODF·운영 정규화가 필요할 때만. 변환 이후는 [04-xlsx.md](04-xlsx.md)와 같다.

```bash
soffice --headless --norestore --nolockcheck \
  --convert-to xlsx:"Calc MS Excel 2007 XML" \
  --outdir /data/normalized \
  monthly_kpi.ods
```

한글 폰트, soffice 워커 하나, 타임아웃, `failed_ods` 큐는 [05-xls.md](05-xls.md)와 같다. odfpy로 직접 읽으면 날짜·병합·반복 열이 깨지기 쉽다. 표본 20개로 행 수·한글을 비교하고 엔진은 calamine으로 고정한다.

### 3. 여러 시트는 여러 랜딩

시트마다 Parquet 하나, 또는 한 파일에 `sheet_name` 컬럼. 월보 표지·집계·원장을 한 UNION으로 합치지 않는다. 피벗 흉내 시트는 04처럼 건너뛴다.

원인/대책 긴 칸은 테이블에 남긴다. RAG 복제는 그 열만. ODS 전체를 임베딩하지 않는다.

### 4. MCP는 정형

Codex CLI에는 `query_tables`다. `search_passages`로 셀을 찾지 않는다. LIMIT 강제. 3,100개 파일 테이블을 만들지 않는다.

## 흔한 실패

- unzip 후 XML 태그를 청크한다
- ODT 파이프라인(가족 A)에 넣어 표가 문단이 된다
- Docling 마크다운 표로 보내 숫자가 틀린다
- 여러 시트를 한 테이블로 붙여 Grain이 사라진다
- 한글 폰트 없이 변환해 품번이 `□□`
- 원본을 지워 재변환이 안 된다
- 행을 Milvus에 넣어 집계 MCP가 비는 것

## 하지 말 것

- `.ods`를 텍스트/마크다운 dump 후 임베딩
- `content.xml`을 19-xml 문서 분기로 보내기
- 웹 변환 API에 사내 원장 업로드
- 변환 실패 파일을 빈 Parquet로 적재
- 원본 `.ods` 삭제
- `SELECT *`를 Codex에 열어 두기

## 인접 포맷

- `.xlsx` → [04-xlsx.md](04-xlsx.md). calamine 직접 또는 변환 후 도착점
- `.xls`/`.xlsb`/`.xlsm` → [05-xls.md](05-xls.md), [22-xlsb.md](22-xlsb.md), [21-xlsm.md](21-xlsm.md)
- `.odt` → [25-odt.md](25-odt.md). 같은 ODF ZIP, 가족 A
- `.csv`/`.tsv` → [06-csv.md](06-csv.md), [23-tsv.md](23-tsv.md)
- `.odp` → [26-odp.md](26-odp.md). 슬라이드. 여기 아님
