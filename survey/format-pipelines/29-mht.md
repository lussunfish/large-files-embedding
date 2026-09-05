# .mht 권장 파이프라인

- 배경: 시장품질 포털·클레임 시스템·사내 공지를 IE/Outlook에서 “웹 페이지, 보관 파일”로 저장한 `.mht`/`.mhtml`을 RAG/MCP에 넣을 때 MIME을 먼저 푼다.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

`.mht`/`.mhtml`은 가족 G다. 서술 HTML이 아니라 **MIME multipart 컨테이너**다. `text/html` 파트를 꺼내 [13-html.md](13-html.md)로 보내고, `cid` 이미지는 [17-png-jpeg.md](17-png-jpeg.md)로 보낸다. `.mht`와 `.mhtml`은 같다. base64 원문을 인덱스에 넣지 않는다. headless Chrome은 기본이 아니다.

Docling 지원 목록(2026-09)에 MHT/MHTML이 없다. EML/MSG email 백엔드로 넣지 않는다. MIME에서 HTML을 꺼내는 경로가 맞다.

권장 한 줄:

```
.mht / .mhtml → MIME multipart 파싱
             → text/html → 13-html (크롬 제거 + 헤딩 청크)
             → cid 이미지 → 17-png-jpeg
             → 기타 첨부는 포맷 라우터
             → MCP: get_outline / get_section (HTML) + 이미지 위임
```

| 선택 | 판단 |
|---|---|
| MHTML 파일 전체를 임베딩 | 하지 말 것. boundary·base64가 본문보다 큼 |
| MIME에서 HTML 파트만 추출 후 13 | **기본 경로** |
| cid 이미지를 본문 텍스트로 취급 | 하지 말 것. 17번으로 |
| headless Chrome/Playwright로 렌더 | 기본 아님. XSS·내부망 요청 |
| PDF 인쇄 후 StandardPdfPipeline | 하지 말 것 |
| Docling에 MHT 직접 투입 (email/HTML 백엔드) | 하지 말 것. 지원 목록에 없음 |
| 인코딩을 UTF-8로 고정 | 하지 말 것. EUC-KR/CP949가 흔함 |

## 권장 파이프라인

```
업로드 .mht / .mhtml
  1. 시그니처
       MIME-Version / Content-Type: multipart/related|mixed
       일반 HTML이면 13-html
       OLE면 11-msg, .eml 헤더면 12-eml
       ZIP이면 30-zip
  2. MIME 파싱 (email.parser)
       multipart 트리, charset, Content-Location, Content-ID
       quoted-printable / base64 는 디코드만
  3. 본문 선택
       text/html (또는 text/plain) 파트
       루트 파트(Content-Location이 원 URL)를 우선
  4. 인라인(cid) 이미지
       Content-ID로 본문 <img src="cid:..."> 와 연결
       저장 후 17-png-jpeg
       본문에는 캡션/자리표시만
  5. 본문 HTML
       13-html: 인코딩 → 크롬 제거 → 헤딩/표 청크
  6. 메타
       제품, 차종, 원 URL/파일경로, 문서유형, 저장 일자
  7. MCP
       get_outline, get_section, get_table, search_passages
       이미지는 get_page_image 계열에 위임
```

원본 `.mht`는 보관한다. 인덱스에는 디코드된 HTML 텍스트와 이미지 참조만 남긴다.

## 단계별 권장

### 1. 컨테이너를 먼저 푼다

IE·구 엣지·Outlook은 포털 화면을 `multipart/related`로 저장한다. 파일 앞부분은 헤더와 boundary이고, 본문 HTML 뒤에 PNG/JPEG가 base64로 이어진다. 통째로 임베딩하면 검색 top-k가 `------=_NextPart_`와 `/9j/`로 채워진다.

- Python `email.parser.BytesParser`로 충분하다
- Tika는 보조. HTML 품질이 떨어지면 직접 파서가 낫다
- `.mht`와 `.mhtml`은 확장자만 다르다. 같은 게이트다
- 단일 파트 `text/html`이면 이미 13이다. 컨테이너 취급을 하지 않는다

메일 `.eml`과 비슷하지만 스레드 헤더가 없고, 루트가 웹 페이지다. MSG/EML 파이프라인·Docling email 백엔드로 보내지 않는다.

### 2. 인코딩과 본문 HTML

사내 저장본은 UTF-8이 기본이 아니다.

- 파트 `charset`, HTML `meta charset`, BOM, 추정 순으로 본다
- EUC-KR / CP949 오판은 품번·한글 고장모드를 망가뜨린다
- 선언은 `euc-kr`인데 실제는 UTF-8인 파일이 있다. 모지바케면 재시도한다
- 깨진 파일은 인덱싱하지 않고 `failed_encoding`으로 남긴다

꺼낸 HTML은 [13-html.md](13-html.md)와 같다. 내비·사이드바·로그인 위젯·스크립트를 벗기고 `h1–h3`로 자른다. 표는 table 청크다.

```text
[문서] OO 포털 — 2024년 3월 클레임 공지
[섹션] 2. 조치 현황
[본문] ...
```

### 3. cid 이미지와 base64

`<img src="cid:xxx">` / `Content-Location`으로 붙은 그림은 차트·캡처인 경우가 많다.

- 바이트를 디코드해 파일로 저장하고 부모 HTML에 연결한다
- 역할 판별은 17: 삽입 차트면 VLM 캡션 + OCR 숫자, 페이지 스캔이면 OCR
- base64 문자열 자체를 청크에 넣지 않는다
- CSS·폰트·추적 픽셀·1×1 GIF는 버린다
- 100MB MHT는 이미지가 대부분이다. 본문 HTML만 먼저 인덱싱하고 그림은 상한을 둔다

### 4. 브라우저를 기본으로 켜지 않는다

headless Chrome/Playwright로 `.mht`를 열면 로컬 스크립트가 실행되고, 상대 URL이 내부망을 친다. JS로만 그려지는 대시보드가 아니면 쓰지 않는다. 동적 화면은 원 시스템에서 정적 HTML/CSV를 다시 받는 편이 맞다.

외부 URL을 입고 시점에 다시 fetch하지 않는다. 저장된 파일이 증적이다.

Codex는 HTML 도구를 그대로 쓴다. `search` 하나로 MHT 원문을 넣지 않는다.

## 흔한 실패

- `.mht`를 통째로 넣어 boundary·base64가 본문이 된다.
- Docling email 백엔드에 MHT를 넣어 빈 문서나 메일 헤더로 오인한다.
- CP949를 UTF-8로 읽어 모지바케 임베딩을 만든다.
- cid 차트 JPEG를 건너뛰어 Pareto 숫자가 없다.
- 내비/푸터 반복 문구가 모든 청크 top-k를 차지한다.
- Chrome으로 모든 MHT를 렌더해 입고가 멈추고 XSS 면적이 생긴다.
- HTML `table`을 개행 텍스트로 바꿔 열을 잃는다.

## 하지 말 것

- MHTML 원문(base64 포함)을 하나의 임베딩 단위로 넣기
- Docling email/HTML 백엔드에 `.mht`를 그대로 넣기
- 저장된 페이지의 `<script>` 실행
- PDF 인쇄 후 가족 B로 승격
- 외부 변환/렌더 서비스에 사내 포털 저장본 업로드
- 긴 파일을 통째로 Codex 컨텍스트에 넣기
- `.mht`와 `.mhtml`을 다른 파이프라인으로 쪼개기

## 인접 포맷

- `.html`/`.htm` → [13-html.md](13-html.md). 이 문서의 도착점.
- `.eml` → [12-eml.md](12-eml.md). 같은 MIME, 메일이면 스레드·첨부 분기.
- `.msg` → [11-msg.md](11-msg.md). OLE 메일은 여기로.
- PNG/JPEG → [17-png-jpeg.md](17-png-jpeg.md). cid 그림의 도착점.
- `.zip` → [30-zip.md](30-zip.md). 압축 보관본이지 MIME이 아님.
- 포털에서 받은 `.xlsx` → [04-xlsx.md](04-xlsx.md). HTML이 아니다. RAG 금지.
