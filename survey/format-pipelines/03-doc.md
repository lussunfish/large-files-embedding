# DOC 권장 파이프라인

- 배경: 시장품질 RAG/MCP에서 레거시 Word(`.doc`, 가족 A)를 어떻게 넣을 것인가.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`, `../doc-format-handling.md`

## 결론

`.doc`는 `.docx`와 같은 Word가 아니다. 97–2003 OLE 바이너리라서 python-docx는 직접 못 읽는다. Docling은 LibreOffice가 있으면 내부에서 `convert_to_modern_format`으로 `.docx`로 바꾼 뒤 SimplePipeline을 탄다. 그래도 **입고 단계의 명시적 soffice 게이트가 기본**이다. 타임아웃과 `UserInstallation` 격리를 우리가 통제해야 한다. 변환본은 파생물이고 원본은 보관한다.

권장 한 줄:

```
.doc (원본 보관) → 시그니처 판별 → LibreOffice headless → .docx
                 → SimplePipeline JSON + HybridChunker → Milvus
                 → MCP: outline / section / table
```

| 선택 | 판단 |
|---|---|
| `.doc`를 임베딩에 바로 넣기 | 하지 말 것 |
| Docling 내장 `convert_to_modern_format`만 쓰기 | 기본 아님. timeout·프로필 격리가 약함 |
| `antiword` / `catdoc`으로 텍스트만 뽑기 | 하지 말 것 (표·한글 깨짐) |
| LibreOffice → `.docx` 후 02 파이프라인 | **기본 경로** |
| 변환본만 남기고 원본 삭제 | 하지 말 것 |
| PDF로 먼저 변환 | 기본 경로 아님 |
| 엑셀처럼 Parquet/SQL로 빼기 | 해당 없음. 서술 문서 |

공식 지원 목록에 DOC는 있다. 내부는 여전히 LibreOffice다 (`convert_to_modern_format`). 입고 단계에 변환을 명시해야 실패 원인(soffice 부재 vs 깨진 파일)을 가릴 수 있다. GitHub issue #3819 (2026-07): Docling LibreOffice 호출이 timeout 없이 hang되고 기본 프로필이 충돌한다. 내장 변환을 써도 같다.

## 권장 파이프라인

```
업로드 .doc
  1. 시그니처 확인
       OLE(.doc) / OOXML(가짜 .docx) / RTF({\rtf) 재분류
  2. 정규화
       soffice --headless (+ timeout, UserInstallation 격리) → .docx
       Docling 내장 convert_to_modern_format 은 기본 아님
       원본 보관, 변환본은 파생물
  3. 이후
       02-docx.md 와 동일
       SimplePipeline JSON → HybridChunker(contextualize) → Milvus
  4. MCP
       get_outline, get_section, get_table, search_passages
```

```
업로드
  ├─ 진짜 .doc (OLE)     → LibreOffice → .docx → 02
  ├─ 확장자만 .doc인 OOXML → 이름만 고치고 02
  └─ {\rtf               → 16-rtf.md
```

## 단계별 권장

### 1. 시그니처를 확장자보다 먼저 본다

확장자가 `.doc`인데 실제로는 `.docx`이거나 RTF인 파일이 흔하다.

```bash
file claim_8d.doc
# Word 97-2003 Document   → LibreOffice 변환
# Microsoft Word 2007+    → 확장자만 잘못된 docx. 이름만 고치기
# Rich Text Format        → 16-rtf.md
```

잘못된 확장자를 LibreOffice에 넣으면 실패 원인 추적이 어려워진다.

### 2. 변환은 LibreOffice, 파싱은 Docling

```bash
soffice --headless --norestore --nolockcheck \
  -env:UserInstallation=file:///tmp/lo_profile_$JOB_ID \
  --convert-to docx:"MS Word 2007 XML" \
  --outdir /data/normalized \
  claim_8d.doc
```

운영에서 지킬 것:

- **한글 폰트**를 컨테이너에 넣는다. 없으면 변환은 성공해도 본문이 `□□`가 된다. `fonts-noto-cjk` / `fonts-nanum` 필수.
- LibreOffice는 **스레드 안전하지 않다**. 워커 하나, 또는 파일마다 별도 `UserInstallation`. 대량은 JODConverter 같은 풀.
- 타임아웃을 건다. 깨진 `.doc`가 soffice를 붙잡는다. Docling 내장 변환도 timeout이 없을 수 있다 (#3819).
- 기본 프로필을 공유하지 않는다. 병렬 변환이 기본 `UserInstallation` 락에서 충돌한다 (#3819).
- 변환 실패는 배치를 멈추지 말고 `failed_doc`으로 남긴다.
- 변환된 `.docx`에 `converted_from`, `converter=libreoffice`, `converted_at`을 메타에 남긴다.

### 3. 변환 후는 02와 동일

구조(제목, 표, 리스트)가 중요하면 `.docx`가 맞다. Heading 스타일, HybridChunker(`repeat_table_header=True`, `chunker.contextualize(chunk)`), 표 CSV 분리, `python-docx` 헤더/푸터 품번은 `02-docx.md`를 그대로 쓴다.

PDF로 먼저 보내는 경우는 도장·스탬프·페이지 비전(ColPali)이 필요할 때로 제한한다. 둘 다 하면 비용만 는다.

`.xls`도 같은 LibreOffice 게이트를 탄다. 결과는 `.xlsx`이고 이후는 벡터가 아니라 Parquet/SQL이다. 이 문서의 경로가 아니다.

### 4. MCP

변환 뒤 도구는 `.docx`와 같다. `search` 하나가 아니라 `get_outline`, `get_section`, `get_table`이다. 담당자 인용은 `원본 파일명 + 섹션 경로`를 쓰고, 변환본 경로만 남기지 않는다.

## 흔한 실패

- 가짜 `.doc`(실제 OOXML/RTF)를 OLE 변환에 넣어 실패한다
- 컨테이너에 CJK 폰트가 없어 한글이 `□□`가 된다
- soffice를 병렬로 돌려 프로세스가 죽는다
- 변환 실패 파일을 빈 문서로 인덱싱한다
- 원본을 지워 변환기를 바꿀 수 없다
- 임베디드 엑셀/표가 사라져 표 개수가 원본과 다르다

## 하지 말 것

- `.doc`를 마크다운으로 바로 덤프해서 청크하는 것
- `antiword` / `catdoc`을 기본 추출기로 쓰는 것
- 웹 변환 API에 사내 품질 문서를 올리는 것
- Docling이 `.doc`를 받는다고 입고 로그에 원본만 남기는 것
- Docling 내장 LibreOffice 변환에 timeout·프로필 격리를 맡기는 것
- 변환본만 남기고 원본을 삭제하는 것
- xlsx 행을 Milvus에 넣듯 `.doc` 표를 문장 임베딩하는 것

## 인접 포맷

- 변환 후 파싱·청크·MCP는 `02-docx.md`
- RTF는 시그니처 `{\rtf`. `16-rtf.md`
- 구 엑셀 `.xls`는 같은 게이트지만 가족 C(Parquet/SQL). `05-xls.md`
- PDF 변환은 기본이 아니다. `01-pdf.md`
