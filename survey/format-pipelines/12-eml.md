# MIME EML 권장 파이프라인

- 배경: 시장품질 RAG/MCP에서 `.eml`(MIME) 메일을 어떻게 넣을 것인가
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

`.eml`은 MSG와 같은 **컨테이너**다. 헤더/본문/첨부 분기는 MSG와 같다. base64 원문을 인덱스에 넣지 않는다.

Docling은 2026-09 기준 MIME `.eml`과 Outlook `.msg`를 네이티브로 읽는다 (`mail-parser` extra, `EmailBackendOptions`). **본문 투입은 허용**한다. `list_attachments`는 파일명만 나열하고 첨부 바이트는 넣지 않는다. 이름 목록은 fan-out이 아니다.

| 선택 | 판단 |
|---|---|
| `.eml` 파일 전체를 임베딩 | 하지 말 것. base64 첨부가 본문보다 큼 |
| Docling email 백엔드로 헤더·본문 | **본문 기본 경로** (가족 A형 RAG) |
| `email.parser`로 MIME 트리 분해 | **동등 기본**. charset·cid 제어가 필요할 때 |
| HTML 본문을 태그 채로 청크 | 하지 말 것 |
| text/plain 우선, 없으면 html→text | **기본 경로** |
| EmailBackendOptions.list_attachments만으로 첨부 처리 | 하지 말 것. 바이너리 fan-out 필수 |
| cid 이미지를 본문 텍스트로 취급 | 하지 말 것. 17번으로 |
| 중첩 .eml/.msg 첨부를 한 겹만 풀기 | 하지 말 것. 재귀 unwrap |
| MSG와 다른 MCP | 하지 말 것. 도구를 공유 |

권장 한 줄:

```
.eml (MIME) → Docling email 백엔드 또는 email.parser
  → 헤더 메타 + text/plain(또는 html→text) RAG (가족 A형)
  → 첨부는 디코드 저장 후 포맷 라우터
    (xlsx→04, pdf→01, png→17, 중첩 eml/msg→재귀)
  → MCP: get_email / list_attachments 후 위임
```

## 권장 파이프라인

```
업로드 .eml
  1. 시그니처
       From/Received/MIME-Version 헤더 아니면 재분류
       OLE CFB면 11-msg로
  2. 헤더·본문
       Docling email 백엔드 (mail-parser extra)
         또는 Python email.parser.BytesParser
       multipart/mixed, alternative, related 트리
       charset 디코드 (utf-8, euc-kr, cp949, iso-2022-kr)
       본문 RAG: 메일 1통 = 문서 1개 (가족 A형)
  3. 본문 선택
       text/plain 우선
       없으면 text/html → html-to-text
       quoted-printable / base64 디코드는 파서 단계만
  4. 인라인(cid) 이미지
       Content-ID로 본문 위치와 연결
       저장 후 17-png-jpeg
  5. 첨부 fan-out (Docling과 별도, 필수)
       list_attachments 이름 목록은 힌트일 뿐
       Content-Disposition=attachment 디코드 저장
       시그니처로 포맷 라우터 (MSG와 동일)
       msg/eml 첨부 → 재귀 unwrap (깊이 제한)
  6. 스레드
       Message-ID / In-Reply-To / References
  7. MCP
       get_email, list_attachments, get_thread
       첨부 도구에 위임
```

원본 `.eml`은 보관한다. 인덱스에는 디코드된 텍스트와 첨부 참조만 남긴다.

## 단계별 권장

### 1. 파싱: 본문은 Docling 또는 MIME 트리

`.eml`은 텍스트 헤더 + MIME 파트다. OLE가 아니다.

- Docling email 백엔드: 헤더·본문을 `DoclingDocument`로 받는다. 첨부 바이트는 오지 않는다
- 표준 라이브러리 `email.parser.BytesParser`: charset·cid·중첩 파트를 직접 통제할 때
- Tika는 보조. HTML 본문 품질이 떨어지면 직접 파서가 낫다
- `multipart/alternative`는 같은 본문의 중복이다. plain과 html을 둘 다 임베딩하지 않는다

charset을 헤더만 믿지 않는다. `euc-kr`로 선언하고 실제는 `utf-8`인 사내 메일이 있다. 모지바케면 후보 인코딩을 재시도한다.

### 2. 본문: plain 우선, html은 변환 (가족 A형)

품질 메일은 회신 인용과 서명이 HTML 테이블인 경우가 많다.

1. `text/plain`이 있으면 그걸 본문으로 쓴다
2. 없으면 HTML을 텍스트로 바꾼다. 브라우저 렌더는 기본 경로가 아니다
3. `<img src="cid:...">`는 그림 자리만 표시하고, 바이트는 이미지 파이프라인으로 보낸다
4. 스타일·스크립트·추적 픽셀은 버린다

본문 RAG 단위는 메일 1통이다. MSG와 같다. 서술 텍스트이므로 가족 A처럼 임베딩하고, 첨부는 재입고한다.

### 3. base64를 인덱스에 넣지 말 것

`.eml` 용량의 대부분이 첨부 base64다. 원문 파일을 청크하면 검색이 `AAAA` 덩어리가 된다.

- 인덱싱 대상은 디코드된 본문과 헤더 메타뿐이다
- 첨부는 바이너리로 저장한 뒤 포맷별 파이프라인에 넣는다
- 100MB xlsx 첨부는 메일 파서가 아니라 04-xlsx 스트리밍이 연다
- Docling이 본문을 읽어도 첨부 fan-out을 생략하지 않는다

### 4. cid 이미지와 중첩 메일

서명 로고와 본문 차트/사진이 섞인다.

- 로고·배너는 스킵한다 (작은 픽셀, 반복 cid)
- Pareto·공정 사진·스캔 표는 17번으로 보낸다. 부모는 메일 id, 캡션은 주변 문장
- cid를 `[image: image001.png]` 텍스트로만 남기면 차트 숫자가 사라진다
- 첨부가 `.eml`/`.msg`이면 깊이 제한을 두고 이 문서·11번으로 재귀한다

### 5. 스레드와 메타

`Message-ID`, `In-Reply-To`, `References`가 RFC 표준이다. Outlook `Thread-Index`가 있으면 MSG와 같이 conversation에 붙인다.

메타: 발신, 수신, 일자, subject, 제품/차종/클레임번호, `parser=docling|email.parser`, `container=eml`.

PII·내부메일 주의는 MSG와 동일하다. 업무 메일함만 넣고 외부 API에 원문을 올리지 않는다.

### 6. MCP

MSG와 **같은 도구**를 쓴다. 컨테이너 포맷이 달라도 담당자에게는 메일이다.

1. `get_email(message_id)`
2. `list_attachments(message_id)`
3. `get_thread(conversation_id)`
4. 첨부 성격에 따라 `query_tables` / `get_page_image` / `get_section`에 위임

## 흔한 실패

- `.eml` 원문을 줄 단위로 잘라 base64가 청크가 됨
- Docling 본문만 넣고 첨부 fan-out을 생략함
- html과 plain을 둘 다 임베딩해 같은 문장이 두 번 검색됨
- `euc-kr` 본문이 깨진 채 인덱싱
- cid 차트 숫자를 본문에서 잃어버린 채 답변
- 중첩 .eml/.msg를 한 겹만 풂
- 헤더 접힌 줄(folded line)을 제목 일부로 오인

## 하지 말 것

- base64 페이로드를 임베딩·BM25에 넣기
- HTML을 브라우저로 렌더한 뒤 PDF로 보내 Docling
- Docling 첨부 이름 목록을 fan-out 대체로 쓰기
- MSG 파이프라인과 다른 청크/MCP를 만들기
- 첨부 없이 제목만 넣고 “메일 입고 완료”로 표시하기
- 외부 변환 API에 사내 `.eml` 업로드

## 인접 포맷

- `.msg` → [11-msg.md](11-msg.md). 분기·MCP 공유
- HTML 파일만 온 경우 → [13-html.md](13-html.md). 메일이 아니면 가족 E
- 첨부·cid 이미지 → [17-png-jpeg.md](17-png-jpeg.md)
- 첨부 XLSX → [04-xlsx.md](04-xlsx.md)
- 첨부 TIFF → [18-tiff.md](18-tiff.md)
