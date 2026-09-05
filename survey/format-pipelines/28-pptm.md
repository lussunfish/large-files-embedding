# .pptm 권장 파이프라인

- 배경: 시장품질 월간보고·자동집계 덱이 매크로 사용 PowerPoint(`.pptm`)로 올 때, VBA는 실행하지 않고 슬라이드만 가족 D로 넣는다.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

`.pptm`은 가족 D다. OOXML은 `.pptx`와 같고, 차이는 `ppt/vbaProject.bin`이다. **매크로를 실행하지 않는다.** VBA를 제거한 뒤 [07-pptx.md](07-pptx.md)를 탄다. 슬라이드 1장 = 청크 1개다. 전 장을 평탄화하지 않는다. 차트 규칙은 07과 같다.

권장 한 줄:

```
.pptm → 시그니처(ZIP/OOXML) 확인
      → vbaProject.bin 제거 (실행 금지)
      → Docling PPTX 백엔드 (python-pptx)
      → 슬라이드 단위 청크(제목+본문+노트+차트캡션)
      → 표는 table 객체
      → bar/pie/line: Docling chart extraction, 사진·공정: VLM
      → MCP: list_slides / get_slide(n)
```

| 선택 | 판단 |
|---|---|
| 매크로 실행 후 차트·숫자를 갱신 | 하지 말 것. 실행 금지 |
| VBA를 본문과 같이 임베딩 | 하지 말 것 |
| 매크로 제거 후 07-pptx | **기본 경로** |
| 전 슬라이드를 한 blob으로 dump | 하지 말 것 |
| PDF로 변환 후 StandardPdfPipeline | 기본 경로 아님 |
| OLE `.ppt`를 python-pptx에 투입 | 하지 말 것. 08로 |

## 권장 파이프라인

```
업로드 .pptm
  1. 시그니처
       ZIP/OOXML + ppt/slides            → .pptm/.pptx
       ppt/vbaProject.bin 있으면 매크로 표시
       OLE CFB                           → 08-ppt
       ODF mimetype presentation         → 26-odp
  2. 매크로 격리
       원본 .pptm 보관
       vbaProject.bin 제거, Content_Types 정리
       PowerPoint COM/LibreOffice 매크로 호출 금지
  3. 이후는 07-pptx 와 동일
       Docling PPTX 파싱 (python-pptx)
       슬라이드 1장 = 1청크
       표 객체
       bar/pie/line → chart understanding
       사진·공정 이미지 → VLM
  4. 메타
       제품, 차종, 문서유형, 기간, slide_index
       macros_stripped=true, original_ext=pptm
  5. MCP
       list_slides, get_slide(n), search_passages, get_table
```

원본 `.pptm`과 매크로 제거본을 둘 다 보관한다. 변환·파싱 JSON도 남긴다.

## 단계별 권장

### 1. 시그니처: ZIP/OOXML

`.pptm`은 `.pptx`와 같은 압축 패키지다. python-pptx는 OLE `.ppt`를 읽지 못한다.

```bash
file monthly_review.pptm
# Microsoft PowerPoint 2007+ (ZIP)  → 이 문서
# PowerPoint 97-2003 (OLE)          → 08-ppt
# OpenDocument Presentation         → 26-odp
```

`ppt/presentation.xml`과 `ppt/slides/slideN.xml`이 본문이다. 확장자가 `.pptx`여도 `vbaProject.bin`이 있으면 `.pptm`과 같이 취급한다. 실제가 `.docm`/`.xlsm`이면 재분류한다.

### 2. 매크로는 제거만 한다. 실행하지 않는다

월보 템플릿 VBA는 클레임 원장·품질 DB에서 숫자를 당겨 차트를 다시 그린다. 입고 워커가 실행하면 내부망 조회와 파일 쓰기가 생긴다. 저장된 슬라이드 스냅샷이 증적이다. 실행해서 “최신값”을 만들지 않는다.

- COM AutoOpen, LibreOffice 매크로, 외부 매크로 분석 서비스 금지
- 파서는 슬라이드 XML·노트·임베디드 이미지만 읽는다
- 매크로가 채우기로 한 자리라도, 파일이 비어 있으면 빈 채로 둔다
- VBA 모듈·폼은 품질 지식이 아니다. 인덱싱하지 않는다

서명된 매크로도 입고에서는 실행하지 않는다.

### 3. 이후는 가족 D

제거본은 `.pptx`다. 청크 규칙은 07과 같다.

```text
[문서] 2024-09 OO 차종 시장품질 월간보고
[슬라이드] 12 / 원인분석 — 누유
[본문] ...
[노트] ...
[차트] Pareto: 누유 42%, 이음 21% ...
```

- 슬라이드 1장 = 청크 1개. 다른 장과 합치지 않는다
- 발표자 노트를 버리지 않는다. 원인·대책이 노트에만 있는 경우가 많다
- bar/pie/line은 Docling chart understanding (그림 → 표). 사진·공정 이미지는 VLM
- 표는 table 객체. 문장으로 평탄화하지 않는다
- 마스터 반복 문구는 메타로만

한 장이 임베딩 한도를 넘으면 같은 `slide_index` 안에서만 나눈다. 100MB급 임베디드 영상·고해상 차트는 이미지 파이프라인([17-png-jpeg.md](17-png-jpeg.md))으로 빼고 슬라이드 청크에는 캡션만 남긴다.

### 4. MCP

`search` 하나만 두지 않는다. Codex는 슬라이드 목록을 보고 해당 장만 읽는다.

1. `list_slides(doc_id)` — 번호, 제목, 차트 여부
2. `get_slide(doc_id, n)` — 본문+노트+표+캡션
3. `search_passages(query, filters)` — `slide_index` 필터
4. `get_table(doc_id, slide_index, table_id)`

인용은 `파일명 + 슬라이드 n`이다. 매크로 모듈명은 인용하지 않는다. PDF 변환은 비전 검색이 필요할 때만 ([01-pdf.md](01-pdf.md)).

## 흔한 실패

- 입고 시 매크로를 실행해 DB에서 숫자를 덮어 쓴다. 증적과 검색이 어긋난다.
- VBA 바이너리를 텍스트로 넣어 청크가 오염된다.
- 전 슬라이드를 한 청크로 붙여 품번·대책이 교차한다.
- 노트를 버려 화면에 없는 근본원인이 없다.
- 차트 이미지를 스킵해 Pareto 숫자가 없다.
- 확장자만 보고 `.ppt` OLE를 python-pptx에 넣는다.

## 하지 말 것

- `.pptm` 매크로 실행
- 슬라이드 평탄화 후 토큰 윈도우 자르기
- `.pptm → PDF → StandardPdfPipeline`을 기본으로 쓰기
- 웹 변환 API에 사내 덱 업로드
- 빈 매크로 템플릿을 본문처럼 임베딩
- 원본 삭제
- MCP를 `search` 하나로 끝내기

`.pptm`은 07의 변형이다. 게이트는 매크로 제거이고, 청크는 슬라이드다.

## 인접 포맷

- `.pptx` → [07-pptx.md](07-pptx.md). 이 문서의 도착점.
- `.ppt` → [08-ppt.md](08-ppt.md). OLE면 여기로. 변환 후에도 매크로는 실행하지 않는다.
- `.docm` → [27-docm.md](27-docm.md). 같은 매크로 게이트, 도착은 가족 A.
- `.xlsm` → [21-xlsm.md](21-xlsm.md). 같은 게이트, 도착은 가족 C (RAG 금지).
- `.odp` → [26-odp.md](26-odp.md). ODF 슬라이드. Docling ODP가 우선.
- 배포 PDF 덱 → [01-pdf.md](01-pdf.md).
