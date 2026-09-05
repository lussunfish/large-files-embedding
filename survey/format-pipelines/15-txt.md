# TXT 권장 파이프라인

- 배경: 시장품질 RAG/MCP에서 평문(`.txt`, 가족 E)을 어떻게 넣을 것인가. 가벼운 텍스트이지 PDF가 아니다.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

`.txt`의 기본은 Docling이 아니다. 인코딩을 먼저 보고, 문단·빈 줄 기준으로 나눈다. 고정 512토큰 창은 기본이 아니다. 내용이 CSV·로그·RTF면 재분류한다. 파일명에서 품번·차종·기간을 메타로 뽑는다. 통합 `DoclingDocument` JSON이 필요할 때만 Docling 텍스트 백엔드를 선택으로 켠다.

권장 한 줄:

```
.txt → 시그니처/인코딩(cp949, euc-kr, utf-8-sig) → 내용 재분류
     → 서술이면 문단 분할 + 파일명 메타 → Milvus
     → MCP: search_passages / get_section(문단 그룹)
```

| 선택 | 판단 |
|---|---|
| Docling StandardPdfPipeline | 하지 말 것. 과함 |
| Docling 텍스트 백엔드 (통합 JSON) | 선택. 기본은 아님 |
| 인코딩 무시 후 utf-8로 읽기 | 하지 말 것. 한글 깨짐 |
| 512토큰 창으로 무조건 자르기 | 기본 경로 아님 |
| 인코딩 감지 + 문단 분할 | **서술 txt 기본** |
| 실제 CSV/로그면 가족 C로 재분류 | **필수** |
| 행을 Milvus에 문장으로 넣기 | CSV면 하지 말 것. Parquet/SQL |

## 권장 파이프라인

```
업로드 .txt
  1. 매직·내용 점검
       {\rtf → 16-rtf.md
       %PDF- → 01-pdf.md
       구분자·헤더 행 → 06-csv.md
       반복 타임스탬프 로그 → 로그 경로
  2. 인코딩
       utf-8-sig / utf-8 / cp949 / euc-kr 순으로 판별
       모지바케면 실패로 남기고 인덱싱하지 않음
  3. 분할
       빈 줄·번호 매기기(1. 1.1 ■) 기준 문단
       제목이 있으면 breadcrumb
       (선택) Docling 텍스트 백엔드 → 통합 JSON
  4. 메타데이터
       파일명에서 제품, 차종, 품번, 기간, 문서유형
  5. 인덱싱
       서술 문단 → Milvus (하이브리드 + 필터)
       표형이면 Parquet/SQL, 벡터 금지
  6. MCP
       search_passages, get_section(문단 범위)
```

원본 `.txt`를 보관한다. 디코딩 결과는 파생물이다. `encoding`, `detected_as=txt|csv|log|rtf`를 메타에 남긴다.

## 단계별 권장

### 1. 확장자만 믿지 않는다

평문에는 강한 매직이 없다. 앞 바이트와 내용을 본다.

- `{\rtf` → RTF. `16-rtf.md`
- `%PDF-` → PDF. `01-pdf.md`
- BOM `EF BB BF` → utf-8-sig
- 탭/쉼표 + 헤더 행이 반복 → CSV. `06-csv.md`

시장품질 업무 메모는 cp949·euc-kr·utf-8-sig가 흔하다. `open(..., encoding="utf-8")` 한 방이 한글을 깨뜨린다. `charset-normalizer` 또는 `chardet`으로 후보를 보고, 한글 비율로 확정한다.

### 2. 분할: 문단이지 토큰 창이 아니다

제목이 있는 md/html이 아니면 빈 줄이 섹션 경계다. 번호 매기기 `1.`, `1.1`, `■ 대책`이 있으면 제목 복원 규칙을 한 겹 둔다.

```text
[문서] 2024_OO차종_VOC메모.txt
[섹션] 대책
[본문] ...
```

긴 메모만 토큰 상한으로 자른다. 자른 뒤에는 앞 문단 제목을 반복한다. 짧은 메모를 512토큰으로 자를 필요는 없다.

### 3. 재분류: CSV·로그는 여기 없다

쉼표/탭 열이 안정적이고 헤더가 있으면 가족 C다. 행을 Milvus에 넣지 않는다. Parquet 1층 → SQL 2층, MCP는 `query_tables`다.

로그 형(타임스탬프 + 레벨 + 메시지)은 문단 RAG보다 필터·키워드가 맞다. 본문 전체를 임베딩하지 않는다.

### 4. 메타데이터는 파일명이 본체

txt에는 헤더/푸터가 없다. `2024_아반떼_ABC-1234_VOC.txt` 같은 이름에서 제품·차종·품번·유형을 정규식으로 뽑는다. 3,100건을 의미 검색만 하면 다른 차종 메모가 올라온다.

LibreOffice, TableFormer, ColPali는 이 포맷에 쓰지 않는다. Docling 텍스트 백엔드는 공식 입력이지만, 서술 메모의 기본 경로는 아니다. 통합 JSON이 필요할 때만 켠다.

### 5. MCP

서술 txt라도 `search`만 두지 않는다. 문단 그룹을 `get_section`으로 읽게 한다. 표형으로 재분류된 파일은 `query_tables`로 보낸다. 인용은 `파일명 + 문단 번호`다.

## 흔한 실패

- utf-8로만 읽어 cp949 본문이 깨진다
- 실제 CSV를 txt로 임베딩해 숫자가 틀린다
- 512토큰 창으로 한 문단을 쪼개 대책이 원인과 섞인다
- RTF/PDF를 txt로 열어 제어 문자가 청크에 남는다
- 파일명 메타 없이 3,100건을 통째로 의미 검색한다
- PDF 파이프라인에 txt를 넣어 빈 JSON이 나온다

## 하지 말 것

- `.txt`를 PDF 파이프라인에 넣는 것
- 짧은 메모까지 Docling을 기본 파서로 강제하는 것
- 인코딩 실패 파일을 인덱싱하는 것
- CSV 행을 Milvus에 넣는 것
- 마크다운도 아닌데 ATX 헤더만 기다리는 것
- 원본을 지우고 디코딩본만 남기는 것

## 인접 포맷

- Markdown은 ATX 헤더 분할. `14-md.md`
- HTML은 본문 추출 후 헤딩 분할. `13-html.md`
- CSV는 인코딩 감지 후 Parquet/SQL. `06-csv.md`
- RTF는 LibreOffice → DOCX. `16-rtf.md`
- PDF/DOCX는 가족 B/A. txt로 다운캐스트하지 않는다. `01-pdf.md`, `02-docx.md`
