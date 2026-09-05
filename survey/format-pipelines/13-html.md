# .html 권장 파이프라인

- 배경: 시장품질 포털 저장본, 클레임 시스템 export, 사내 공지 HTML을 RAG/MCP에 넣을 때 크롬(내비/광고)을 먼저 벗긴다.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

`.html`/`.htm`은 가족 E다. PDF 레이아웃 모델을 돌리지 않는다. **본문만 남기고 헤딩 기준으로 자른다.** 내비·사이드바·광고·스크립트는 청크가 아니다. 내부 보고서 HTML은 Docling HTML 백엔드(`HTMLDocumentBackend`, bs4)가 공식 경로다. 웹 저장본의 크롬(내비/광고)은 readability/trafilatura가 먼저다. headless Chrome은 기본이 아니다.

권장 한 줄:

```
.html → 인코딩 감지 → 크롬 제거(readability/trafilatura/BS4)
      → 헤딩 트리 + 표 객체
      → 헤딩 청크 / table 청크 → Milvus
      → MCP: get_outline / get_section / get_table
```

| 선택 | 판단 |
|---|---|
| 페이지 전체 HTML을 그대로 임베딩 | 하지 말 것. 메뉴가 검색을 오염시킨다 |
| readability / trafilatura / BS4 boilerplate 제거 | **기본 경로** (웹 저장본) |
| Docling HTML 백엔드 (bs4) | **내부 보고서·이미 깨끗한 HTML** |
| headless Chrome 렌더 | 기본 아님. 느리고 XSS 면적이 생긴다 |
| 표를 문장으로 평탄화 | 하지 말 것 |
| PDF 인쇄 후 StandardPdfPipeline | 하지 말 것 |

## 권장 파이프라인

```
업로드 .html / .htm / .mhtml / .mht
  1. 컨테이너
       mhtml/mht → 본문 HTML 파트 추출
       일반 html → 그대로
  2. 인코딩
       BOM, meta charset, chardet
       EUC-KR / CP949 가 사내 저장본에 흔함
  3. 본문 추출
       웹 저장본 → trafilatura / readability
       내부 보고서 → Docling HTML 또는 BS4
       script/style/nav/footer 제거
  4. 구조
       h1–h3 트리, 문단, 리스트
       table → table 청크
  5. 메타
       제품, 차종, URL/파일경로, 문서유형
  6. MCP
       get_outline, get_section, get_table, search_passages
```

## 단계별 권장

### 1. 크롬을 벗긴다

품질 포털에서 “다른 이름으로 저장”한 HTML은 메뉴, 로그인 위젯, 관련 문서 목록이 본문보다 길다. 그대로 임베딩하면 “클레임 현황” 검색에 사이드바 링크가 올라온다.

- 웹 저장본: `trafilatura` 또는 readability 계열. 크롬을 벗긴 뒤에 헤딩 분할한다. Docling HTML 백엔드는 내비/푸터를 본문으로 남길 수 있다.
- 구조가 단순한 사내 보고서: BeautifulSoup로 `nav`, `aside`, `footer`, `script` 제거하거나, 이미 깨끗하면 Docling HTML 백엔드.
- 이미 본문만 있는 export는 Docling HTML 백엔드가 표·헤딩을 `DoclingDocument`로 남긴다. 통합 JSON이 필요하면 이쪽이다.

### 2. 청크는 헤딩

가족 E는 HybridChunker까지 필요 없는 경우가 많다. `h1/h2/h3`가 섹션이다.

```text
[문서] OO 포털 — 2024년 3월 클레임 공지
[섹션] 2. 조치 현황
[본문] ...
```

헤딩이 없으면 문단 단위로 자른다. 고정 토큰 윈도우는 마지막이다.

표는 HTML `table`을 table 청크로 유지한다. 헤더 행을 각 조각에 반복한다. 시장품질 공지의 집계표는 여기가 본체다.

### 3. MHTML과 인코딩

Outlook·IE·구 인트라넷은 `.mht`/`.mhtml`을 남긴다. MIME 안에서 `text/html` 파트를 꺼낸다. 관련 이미지는 필요할 때만 저장한다. MHTML 전체를 텍스트로 넣지 않는다.

인코딩은 UTF-8이 기본이 아니다.

- `meta charset`, BOM, 추정 순으로 본다.
- EUC-KR/CP949 오판은 품번·한글 고장모드를 망가뜨린다.
- 깨진 파일은 인덱싱하지 않고 `failed_encoding`으로 남긴다.

### 4. 브라우저를 기본으로 켜지 않는다

headless Chrome/Playwright는 느리고, 로컬 HTML의 스크립트를 실행하면 XSS·내부망 요청이 생긴다. JS로만 그려지는 대시보드가 아니면 쓰지 않는다. 동적 페이지는 원 시스템에서 정적 HTML/CSV를 다시 받는 편이 맞다.

외부 URL을 입고 시점에 다시 fetch하지 않는다. 저장된 파일이 증적이다.

## 흔한 실패

- 내비/푸터 반복 문구가 모든 청크 top-k를 차지한다.
- CP949를 UTF-8로 읽어 모지바케 임베딩을 만든다.
- `.mht`를 통째로 넣어 boundary 문자열이 본문이 된다.
- `<table>`을 개행 텍스트로 바꿔 열을 잃는다.
- Chrome으로 모든 HTML을 렌더해 입고가 멈춘다.

## 하지 말 것

- PDF 인쇄 후 가족 B로 승격
- 페이지 소스 전체를 하나의 청크로 임베딩
- 저장된 HTML의 `<script>` 실행
- 외부 변환/렌더 서비스에 사내 페이지 업로드
- 긴 파일을 통째로 Codex 컨텍스트에 넣기

## 인접 포맷

- `.md` → [14-md.md](14-md.md). 같은 가족 E. 헤더 분할이 기본. Docling은 통합 JSON이 필요할 때만.
- `.txt` → [15-txt.md](15-txt.md). 인코딩+문단.
- `.xml` → [19-xml.md](19-xml.md). 스키마 있으면 정형.
- 포털에서 받은 `.xlsx` → [04-xlsx.md](04-xlsx.md). HTML이 아니다. RAG 금지.
