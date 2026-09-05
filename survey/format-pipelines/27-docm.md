# .docm 권장 파이프라인

- 배경: 시장품질 8D·대책서·클레임 템플릿이 매크로 사용 Word(`.docm`)로 올 때, VBA는 실행하지 않고 본문만 가족 A로 넣는다.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`, `../docx-pipeline.md`

## 결론

`.docm`은 가족 A다. OOXML은 `.docx`와 같고, 차이는 `word/vbaProject.bin`이다. **매크로를 실행하지 않는다.** VBA를 제거한 뒤 [02-docx.md](02-docx.md)와 동일하게 탄다. Docling은 ZIP/OOXML이면 확장자와 무관하게 `MsWordDocumentBackend`(docx)로 읽는다. 이름을 `.docx`로 바꿔도, ZIP으로 열어도 같다. 그래도 VBA 파트는 먼저 뺀다. 시그니처는 ZIP이다. 실제가 OLE `.doc`이면 [03-doc.md](03-doc.md)로 보낸다.

권장 한 줄:

```
.docm → 시그니처(ZIP/OOXML) 확인
      → vbaProject.bin 제거 (실행 금지)
      → Docling SimplePipeline (docx 백엔드) → JSON 원본 보관
      → HybridChunker(contextualize + 표 분리) → Milvus
      → MCP: outline / section / table
```

| 선택 | 판단 |
|---|---|
| 매크로 실행 후 채워진 본문을 수집 | 하지 말 것. 실행 금지 |
| VBA 소스를 청크로 임베딩 | 하지 말 것. 코드는 품질 지식이 아님 |
| 매크로 제거 후 02-docx | **기본 경로** |
| PDF로 변환 후 StandardPdfPipeline | 기본 경로 아님 |
| 확장자만 보고 python-docx에 OLE `.doc` 투입 | 하지 말 것. 03으로 |
| 원본을 지우고 매크로 제거본만 남기기 | 하지 말 것 |

## 권장 파이프라인

```
업로드 .docm
  1. 시그니처
       ZIP/OOXML + word/document.xml     → .docm/.docx
       word/vbaProject.bin 있으면 매크로 표시
       OLE CFB (D0 CF 11 E0)             → 03-doc
       RTF ({\rtf)                       → 16-rtf
  2. 매크로 격리
       원본 .docm 보관
       vbaProject.bin / vbaData.xml 제거
       [Content_Types].xml 에서 VBA 파트 삭제
       실행 엔진(WinWord, soffice 매크로) 호출 금지
  3. 이후는 02-docx 와 동일
       Docling SimplePipeline JSON (docx와 동일 백엔드)
       HybridChunker + chunker.contextualize(chunk)
       표는 table 청크, repeat_table_header=True
  4. 메타
       제품, 차종, 품번, 문서유형, 기간, 섹션 경로
       macros_stripped=true, original_ext=docm
  5. MCP
       get_outline, get_section, get_table, search_passages
```

원본 `.docm`과 매크로 제거본·JSON을 모두 보관한다. 청크만 남기면 청킹 전략을 바꿀 때 다시 파싱해야 한다.

## 단계별 권장

### 1. 시그니처: ZIP이지 OLE가 아니다

사내 공유 폴더에는 `.docm`인데 실제로는 `.doc`이거나, `.docx`인데 매크로가 들어 있는 파일이 있다.

```bash
file 8d_template.docm
# Microsoft Word 2007+ (ZIP/OOXML)  → 이 문서
# Composite Document File V2 (OLE)  → 03-doc
# PDF document                      → 01-pdf
```

ZIP이면 `word/document.xml`이 본문이다. `vbaProject.bin`은 바이너리 VBA 프로젝트다. 이 파트를 임베딩 입력으로 열지 않는다. 확장자 `.docx`여도 `vbaProject.bin`이 있으면 `.docm`과 같이 취급한다.

### 2. 매크로는 제거만 한다. 실행하지 않는다

품질 템플릿 매크로는 양식 보호, 품번 조회, 사내 DB 호출을 한다. 입고 워커가 그걸 실행하면 내부망 요청·파일 쓰기가 생긴다. 악성 `.docm`도 같은 확장자다.

- Word/Excel COM, LibreOffice 매크로, `win32com` AutoOpen을 켜지 않는다
- 파싱은 `document.xml`·스타일·표만 읽는다. python-docx/Docling은 VBA를 실행하지 않는 경로를 쓴다
- 제거는 ZIP에서 VBA 파트를 빼고 Content_Types를 고치는 정도면 충분하다
- 제거본을 `.docx`로 바꿔도 Docling 백엔드는 같다. 매크로를 남긴 채 확장자만 바꾸지 않는다
- 매크로가 런타임에 채우는 필드가 비어 있으면 빈 칸으로 둔다. 실행해서 채우지 않는다
- 외부 샌드박스에 사내 `.docm`을 올려 매크로를 “분석”하지 않는다

서명된 매크로든 아니든 RAG 입고에서는 동일하다. 신뢰 여부와 실행은 별개다.

### 3. 이후는 가족 A

매크로를 뺀 문서는 `.docx`다. Docling은 이 ZIP을 docx와 같이 파싱한다. PDF용 `StandardPdfPipeline`은 쓰지 않는다.

- HybridChunker + 제목 경로. 임베딩은 `chunker.contextualize(chunk)`
- 표는 CSV/Markdown 별도 청크, `repeat_table_header=True`
- 머리글·바닥글 반복 문구는 메타로만
- 8D의 `현상 / 원인 / 대책` 절이 청크 경계다

본문이 거의 없고 ActiveX 컨트롤·폼만 있는 템플릿은 빈 문서로 인덱싱하지 않는다. `failed_empty_docm`으로 남기고, 채워진 제출본이 있는지 본다.

### 4. MCP

Codex는 매크로 안내가 아니라 섹션을 읽는다.

1. `get_outline(doc_id)` — 제목 트리
2. `get_section(doc_id, path)` — 본문
3. `get_table(doc_id, table_id)`
4. `search_passages(query, filters)`

인용은 `파일명 + 섹션 경로`다. VBA 모듈명은 인용 단위가 아니다.

## 흔한 실패

- 확장자만 보고 OLE `.doc`을 python-docx에 넣어 즉시 실패한다.
- 입고 서버에서 매크로를 실행해 내부 API를 친다.
- `vbaProject.bin`을 텍스트로 디코딩해 청크에 바이너리 잔해가 남는다.
- 빈 템플릿을 본문과 같이 임베딩해 “8D” 검색에 양식만 올라온다.
- 매크로 제거본만 남기고 원본을 지워 증적이 사라진다.
- 실제 `.xlsm`/`.pptm`을 Word 파이프라인에 넣는다.

## 하지 말 것

- `.docm` 매크로 실행 (로컬이든 가상 머신이든 입고 경로에서 금지)
- VBA 코드를 품질 지식으로 임베딩
- PDF로 바꿔 가족 B에 넣는 것을 기본으로 두기
- 웹 변환 API에 사내 매크로 문서 업로드
- 원본 삭제
- MCP를 `search` 하나로 끝내기

`.docm`은 포맷 문제가 아니라 **실행 면적을 먼저 줄이는 게이트**다. 이후는 02와 같다.

## 인접 포맷

- `.docx` → [02-docx.md](02-docx.md). 이 문서의 도착점.
- `.doc` → [03-doc.md](03-doc.md). OLE면 여기로. 매크로여도 실행하지 않는다.
- `.pptm` → [28-pptm.md](28-pptm.md). 같은 매크로 게이트, 도착은 가족 D.
- `.xlsm` → [21-xlsm.md](21-xlsm.md). 같은 게이트, 도착은 가족 C (RAG 금지).
- `.rtf` → [16-rtf.md](16-rtf.md). 시그니처가 `{\rtf` 이면 재분류.
- `.odt` → [25-odt.md](25-odt.md). 매크로 없는 ODF Word형.
