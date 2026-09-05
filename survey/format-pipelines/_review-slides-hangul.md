# 슬라이드·한글 파이프라인 리뷰 (2026-09)

대상: `07-pptx.md`, `08-ppt.md`, `09-hwp.md`, `10-hwpx.md`, `26-odp.md`, `28-pptm.md`, `37-cell.md`, `38-show.md`.  
체: 하다/다. 패치는 위 파일에 반영했다.

## 한 줄

슬라이드 쪽은 Docling이 이미 읽고 있었고, 빠진 것은 차트 분기와 ODP 우선순위다. 한글 쪽은 pyhwp 폴백이 낡았고, Docling 미지원은 그대로다.

## 파일별 발견과 패치

### 07-pptx.md — 차트만 고침. 슬라이드=청크는 유지

**이전.** Docling PPTX + 슬라이드 1장=청크는 맞았다. 차트는 “보통 그림 → VLM 한 줄”로만 적혀 있었다.

**사실 (2026-09).** Docling PPTX는 `python-pptx` 네이티브다. chart understanding enrichment가 bar/pie/line 그림을 표로 올린다 (`PictureItem.meta.tabular_chart.chart_data`). 사진·공정 이미지는 그 경로가 아니다.

**패치.** 슬라이드=청크는 유지. bar/pie/line은 chart extraction을 VLM의 대안/보완으로 둔다. 사진·공정·SmartArt는 VLM. 모든 그림을 한쪽으로만 보내지 말 것.

### 08-ppt.md — “Docling이 PPT를 못 읽는다”는 과했다

**이전.** “Docling도 직접 파싱하지 않는다. LibreOffice로 pptx.” UserInstallation·timeout은 이미 있었다.

**사실.** 지원 목록에 PPT가 있다. 조건은 LibreOffice. 내부는 soffice다. issue #3819 (2026-07): soffice 호출에 timeout이 없고, `-env:UserInstallation`이 없어 기본 프로필 잠금으로 병렬 변환이 조용히 실패한다.

**패치.** “Docling이 PPT를 받는다”는 맞되, 입고에서 soffice를 숨기지 않는다. 명시적 LibreOffice → pptx가 기본. UserInstallation + timeout을 명령 예시에 넣는다. 변환 후 07의 차트 분기를 탄다.

### 09-hwp.md — 변환기 순서가 2020년형이었다

**이전.** (1) 한컴 (2) LibreOffice (3) pyhwp 최후. Docling은 “네이티브 파싱이 약하다” 정도.

**사실.** Docling은 HWP를 **지원하지 않는다.** 한컴 공식 블로그(2026-07) 목록은 pyhwp(2020-05 정체, AGPL, HWPX 없음), hwplib/hwpxlib(Java), hwp.js다. 그 목록만 보면 Python이 멈춘다. 더 새 Python: hwpkit(순수 Python, hwp+hwpx), syhwp(MIT, 텍스트/표/md/html), jakal-hwpx(읽기/쓰기). 한컴 무료 HWP→HWPX 변환기는 배치 30.

**패치 순서.**

1. 한컴 공식/COM (있으면)
2. hwpkit 또는 syhwp — Linux/CI 본문+표
3. HWP→HWPX 후 10-hwpx
4. LibreOffice 필터 — 자주 불완전
5. pyhwp 최후, AGPL 주의

pyhwp를 유일한 폴백으로 두지 않는다.

### 10-hwpx.md — unzip은 맞았고, 파서·도착이 부족했다

**이전.** ZIP+XML 직접 읽기 또는 한컴/LibreOffice → DOCX. 라이브러리 이름이 없었다. Docling은 “기대하지 말 것”.

**사실.** unzip OWPML은 유효하다. hwpkit / syhwp / jakal-hwpx가 HWPX를 읽는다. Docling은 HWPX도 파싱하지 않는다. Markdown dump는 표·Heading을 죽인다. HybridChunker는 Word 스타일 트리에 기대는 부분이 크다.

**패치.** 구조 추출 → 가족 A(섹션/table) 매핑이 Linux/CI 기본. Heading 충실도가 필요하면 한컴 → DOCX → 02. Markdown dump 금지. pyhwp는 HWPX를 못 읽는다.

### 26-odp.md — 기본/폴백이 뒤집혀 있었다

**이전.** Docling ODP는 “가능, 검증 후”. LibreOffice → pptx가 **기본 경로**(Docling이 약할 때).

**사실.** Docling은 ODF 프레젠테이션을 네이티브로 읽는다. `OdpDocumentBackend`, 구현은 `odfdo`. PPTX와 같이 슬라이드 경계를 남기면 변환이 필요 없다.

**패치.** OdpDocumentBackend 1순위. LibreOffice → pptx는 실패·노트/표 손실 폴백. 폴백 soffice에도 UserInstallation+timeout. 차트 분기는 07과 같게.

### 28-pptm.md — 게이트는 그대로, 차트만 07에 맞춤

**이전.** 매크로 제거 후 07. 차트는 VLM만.

**사실.** 경로 자체는 맞다. VBA 실행 금지도 맞다.

**패치.** 매크로 스트립 → pptx는 유지. bar/pie/line chart extraction, 사진·공정 VLM을 07과 동기화.

### 37-cell.md / 38-show.md — 한컴 우선은 맞다. Docling 미지원을 못 박음

**이전.** 한컴 → xlsx/pptx, LibreOffice 필터는 차선. Docling 직접 투입 금지.

**사실.** Docling은 `.cell` / `.show`를 파싱하지 않는다. HWP 파서(hwpkit/syhwp)도 셀·쇼용이 아니다. LibreOffice 필터는 있을 때만.

**패치.** 한컴 1순위, LibreOffice 차선 유지. “Docling 네이티브 파싱 없음”을 결론에 명시. 37은 hwpkit/syhwp를 쓰지 말 것. 38 변환 후 차트는 07 분기. `.show`를 ODP 백엔드에 넣지 말 것.

## 유지한 것

- 슬라이드 1장 = 청크 1개. 전 장 평탄화 금지.
- 가족 D MCP: `list_slides` / `get_slide(n)`.
- 원본 보관. 웹 변환 API 금지.
- `.pptm` VBA 미실행.
- `.cell`은 가족 C. RAG 금지. 도착은 04.
- `.hwp`/`.hwpx` 도착은 가족 A 또는 도장일 때 B.

## 고친 오개념

| 구 문장 | 2026-09 |
|---|---|
| 차트는 그림이니 VLM만 | bar/pie/line은 chart understanding, 사진은 VLM |
| Docling은 PPT를 직접 파싱하지 않는다 | LibreOffice가 있으면 받되, soffice 게이트를 숨기지 말 것 |
| ODP는 변환이 기본 | OdpDocumentBackend가 기본, 변환은 폴백 |
| HWP 폴백 = pyhwp | hwpkit/syhwp → HWPX → LO → pyhwp(AGPL) |
| Docling HWP는 “약하다” | **미지원** |
| HWPX는 unzip 또는 한컴만 | unzip + hwpkit/syhwp/jakal, 구조 매핑 우선 |

## 이 패치 밖에 남은 드리프트

`README.md`는 이번 파일 목록 밖이라 손대지 않았다. 아래는 어긋난다.

- 표 #7 PPTX: “노트·차트 분리” → bar/pie/line 표 승격이 빠짐.
- 표 #8 PPT: “LibreOffice → PPTX”는 맞다. Docling 숨김 주의는 08에만 있다.
- 표 #9/#10 HWP/HWPX: “한글로 변환”만. hwpkit/syhwp·구조 매핑이 없다.
- 표 #26 ODP: “슬라이드 1장 = 청크”만. 백엔드 우선이 없다.
- 입고 분기: `ppt/odp/show → 변환 후 D`. ODP는 변환이 기본이 아니다. `pptx/pptm → D`는 맞다. `hwp/hwpx → 한글 변환`은 Linux/CI 추출을 빠뜨린다.

`03-doc.md` / `05-xls.md`의 soffice 게이트는 08과 같은 #3819를 이미 비슷하게 적는다. 명령 예시에 UserInstallation을 넣을지는 별 패치다.

## 근거

- Docling 지원 포맷: PPTX 네이티브, PPT는 LibreOffice 필요, ODT/ODS/ODP 네이티브, HWP/HWPX/CELL/SHOW 없음.
- Chart understanding: 2026-02 Docling 블로그. bar/pie/line → 표.
- LibreOffice: GitHub issue #3819 (2026-07), timeout 없음 + UserInstallation 없음.
- 한컴 블로그 2026-07: pyhwp / hwplib·hwpxlib / hwp.js, 무료 HWP→HWPX 배치 30.
- PyPI/GitHub 2026: hwpkit, syhwp (MIT), jakal-hwpx.
