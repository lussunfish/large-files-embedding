# .show 권장 파이프라인

- 배경: 한국 제조 시장품질 월간보고·8D 요약이 한쇼(`.show`)로 온다. 한셀·한글과 같은 한컴 오피스 패밀리다. 슬라이드 단위를 유지한다.
- 관련 문서: `README.md`, `../market-quality-rag-improvement.md`, [07-pptx.md](07-pptx.md), [09-hwp.md](09-hwp.md)

## 결론

`.show`는 가족 D다. 한컴 프레젠테이션이다. **Docling은 `.show`를 파싱하지 않는다.** python-pptx도 직접 읽지 못한다. **한컴오피스로 `.pptx`로 바꾼 뒤 [07-pptx.md](07-pptx.md)를 탄다.** 슬라이드 1장 = 청크 1개다. LibreOffice 필터는 있을 때만. 원본은 보관한다. 형제 포맷은 `.hwp` / `.hwpx` / `.cell`이다.

권장 한 줄:

```
.show (원본 보관)
  → 시그니처 확인
  → (우선) 한컴오피스 / 한쇼 공식 변환 → .pptx
  → (차선) LibreOffice SHOW 필터 — 있으면, 검증 필수
  → 07-pptx (슬라이드 1장 = 청크 1개)
  → bar/pie/line: Docling chart extraction, 사진·공정: VLM
  → MCP: list_slides / get_slide(n)
```

| 선택 | 판단 |
|---|---|
| python-pptx / Docling에 `.show` 직접 투입 | 하지 말 것. 네이티브 파싱 없음 |
| 한컴 공식 변환 → pptx 후 07 | **기본 경로** |
| LibreOffice SHOW 필터 → pptx | 차선. 슬라이드 수·노트·한글 검증 |
| 전 슬라이드를 한 blob으로 dump | 하지 말 것 |
| PDF로 먼저 보내기 | 기본 아님. 시각 검색이 필요할 때만 |
| antiword / catppt 텍스트 dump | 하지 말 것 |
| 변환본만 남기고 원본 삭제 | 하지 말 것 |

## 권장 파이프라인

```
업로드 .show
  1. 시그니처
       한쇼 패키지/바이너리 → 이 문서
       ZIP/OOXML            → 확장자만 잘못된 pptx. 이름만 고치고 07
       OLE .ppt             → 08-ppt
       %PDF                 → 01-pdf
       한셀/한글 헤더       → 37 / 09. 확장자 위조
  2. 변환기 선택 (위에서 아래로)
       한컴오피스 자동화 / 한쇼 공식 변환
       LibreOffice + SHOW import 필터 (있으면)
  3. 변환 검증
       슬라이드 수, 한글 깨짐, 노트 유무, 표·차트 잔존
  4. 이후는 07-pptx
       슬라이드 청크 + 노트
       bar/pie/line → chart understanding
       사진·공정 이미지 → VLM
  5. 메타
       converted_from=show, converter=hancom|libreoffice
  원본 .show 보관
```

## 단계별 권장

### 1. pptx가 오기 전에는 파싱하지 않는다

한쇼는 OOXML이 아니다. python-pptx는 실패하거나 빈 덱을 만든다. Docling PPTX/ODP 백엔드도 마찬가지다. ODP는 `OdpDocumentBackend`가 있지만 `.show`는 ODF가 아니다. 한글·한셀과 같이 **벤더 변환이 입고 게이트**다.

시장품질 `.show`는 월보·품질회의 자료가 많다. 한 장이 한 이슈다. 변환 전에 텍스트 dump를 하면 표·차트·노트가 한 덩어리가 된다.

웹 변환에 사내 덱을 올리지 않는다.

### 2. 변환기 우선순위

1. **한컴오피스 / 한쇼 공식 변환**  
   Windows에 한컴이 있으면 COM·배치가 표·한글·노트를 가장 잘 살린다. 도착은 `.pptx`다. PDF로 먼저 내리지 않는다. 슬라이드 구조가 사라진다.
2. **LibreOffice SHOW 필터**  
   필터가 있는 이미지에서만. 없는 경우가 많다. 있어도 노트·마스터·차트가 빠진다. 슬라이드 수가 줄면 실패다.
3. **텍스트 추출기**  
   쓰지 않는다. catppt·antiword는 가족 D의 경계를 버린다.

LibreOffice를 쓸 때:

- 한글 폰트(`fonts-noto-cjk` / `fonts-nanum`) 필수
- soffice 워커 하나, 또는 파일마다 `UserInstallation`
- 타임아웃. 깨진 덱이 프로세스를 붙잡는다. issue #3819와 같다
- 실패는 `failed_show`로 남기고 배치를 멈추지 않는다

### 3. 변환 후는 가족 D

청크 규칙은 07과 같다.

- 슬라이드 1장 = 청크 1개
- 제목 + 본문 불릿 + 발표자 노트 + 표 + 차트 캡션
- 마스터 머리글·바닥글은 메타만. 매 장 반복 임베딩 금지
- 한 장이 길면 같은 `slide_index` 안에서만 나눈다

차트는 변환 과정에서 그림이 되기 쉽다. 시리즈 XML을 기대하지 않는다. bar/pie/line은 Docling chart understanding(그림 → 표), 사진·공정 이미지는 VLM. 월보는 차트가 본체다.

### 4. PDF로 가는 경우

기본은 pptx 구조 파싱이다. PDF는 아래만이다.

- ColPali 등 페이지 비전 검색
- 렌더해야만 의미가 있는 다이어그램
- 배포본이 이미 PDF — [01-pdf.md](01-pdf.md)

한쇼를 PDF로 보내는 것을 기본 경로로 두지 않는다. 슬라이드 경계와 노트가 먼저 죽는다.

### 5. MCP

07과 동일한 도구다. 한컴이라고 `search` 하나로 줄이지 않는다.

1. `list_slides(doc_id)` — 번호, 제목, 차트 여부
2. `get_slide(doc_id, n)` — 본문+노트+표+캡션
3. `search_passages(query, filters)` — `slide_index` 필터

인용은 `파일명 + 슬라이드 n`이다.

## 흔한 실패

- python-pptx에 `.show`를 넣어 빈 문서로 인덱싱한다
- Docling이 pptx/odp만 받는다는 로그를 무시하고 원본을 투입한다
- 한글 폰트 없이 변환해 품번·고장모드가 `□□`
- 슬라이드 수는 맞는데 노트가 사라져 원인 서술이 없다
- 전 장을 한 청크로 붙여 품번이 교차한다
- 원본을 지워 한컴 재변환이 불가능하다

## 하지 말 것

- `.show`를 마크다운/텍스트로 바로 dump 해서 청크
- `.show → PDF → StandardPdfPipeline`을 기본으로 쓰기
- 웹 변환 API에 사내 품질 문서 업로드
- 변환 실패 파일을 빈 슬라이드로 인덱싱
- 원본 삭제
- 한셀처럼 Parquet에 넣기 — 슬라이드이지 원장이 아니다

`.show`는 정규화 한 단계다. 게이트만 두면 이후는 07과 같다.

## 인접 포맷

- `.pptx` → [07-pptx.md](07-pptx.md). 이 문서의 도착점.
- `.ppt` → [08-ppt.md](08-ppt.md). 같은 슬라이드 게이트, 벤더는 MS.
- `.odp` → [26-odp.md](26-odp.md). ODF면 Docling ODP가 우선. `.show`는 여기로 보내지 않는다.
- `.hwp` / `.hwpx` → [09-hwp.md](09-hwp.md), [10-hwpx.md](10-hwpx.md). 같은 한컴 우선. 도착은 가족 A.
- `.cell` → [37-cell.md](37-cell.md). 한셀. 도착은 가족 C (04). RAG 금지.
- 배포 PDF 덱 → [01-pdf.md](01-pdf.md). 슬라이드 경계가 페이지다.
- 공정 다이어그램 `.vsdx` → [33-vsdx.md](33-vsdx.md). 가족 H. 한쇼가 아니다.
