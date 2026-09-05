# Outlook MSG 권장 파이프라인

- 배경: 시장품질 RAG/MCP에서 Outlook `.msg`(OLE) 메일을 어떻게 넣을 것인가
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

`.msg`는 서술 문서가 아니라 **컨테이너**다. 헤더·본문은 RAG, 첨부는 포맷 라우터로 다시 보낸다. 바이너리 첨부가 붙은 MSG를 통째로 임베딩하지 않는다.

Docling은 2026-09 기준 EML/MSG를 네이티브로 읽는다 (`mail-parser` extra, `EmailBackendOptions`). **본문 투입은 허용**한다. 다만 `list_attachments`는 파일명(과 있으면 content-type)만 붙이고 첨부 바이트는 넣지 않는다. 이름 목록만으로 첨부를 처리했다고 치지 않는다.

| 선택 | 판단 |
|---|---|
| MSG 파일 전체를 Milvus에 넣기 | 하지 말 것. 첨부 바이너리가 섞임 |
| Docling email 백엔드로 헤더·본문 | **본문 기본 경로** (가족 A형 RAG) |
| extract-msg / Tika로 헤더·본문·첨부 분리 | **동등 기본**. OLE 상세는 이쪽이 낫다 |
| EmailBackendOptions.list_attachments만으로 첨부 처리 | 하지 말 것. 이름만 나옴. 바이너리 fan-out 필수 |
| 본문만 dump하고 첨부 버리기 | 하지 말 것. 품질 메일은 첨부가 본체 |
| 첨부 xlsx를 본문과 같이 청크 | 하지 말 것. xlsx는 SQL |
| In-Reply-To / conversation 무시 | 하지 말 것 |
| 중첩 .msg/.eml 첨부를 한 겹만 풀기 | 하지 말 것. 깊이 제한을 두고 재귀 |

권장 한 줄:

```
.msg (OLE) → Docling email 백엔드 또는 extract-msg / Tika
  → 헤더 메타 + 본문 RAG (가족 A형)
  → 첨부는 원본 바이트로 저장 후 포맷 라우터
    (xlsx→04, pdf→01, png→17, 중첩 msg/eml→재귀)
  → MCP: get_email / list_attachments 후 위임
```

## 권장 파이프라인

```
업로드 .msg
  1. 시그니처
       OLE CFB (D0 CF 11 E0) 아니면 재분류
       내용이 MIME이면 12-eml로
  2. 헤더·본문
       Docling email 백엔드 (mail-parser extra)
         또는 extract-msg / Tika
       From / To / Cc / Date / Subject
       Message-ID / In-Reply-To / References
       Conversation-Index (Outlook 스레드)
       본문 RAG: 메일 1통 = 문서 1개 (가족 A형)
  3. OLE 상세 (필요 시 extract-msg)
       RTF 본문, named properties
       Docling이 놓치면 이 경로가 보조
  4. 첨부 fan-out (Docling과 별도, 필수)
       list_attachments 이름 목록은 힌트일 뿐
       원본 바이트로 저장, parent_id 연결
       시그니처로 포맷 라우터
         xlsx/xls/csv → 가족 C (Parquet/SQL)
         pdf          → 01-pdf
         docx/doc     → 02/03
         png/jpeg     → 17
         tiff         → 18
         msg/eml      → 재귀 unwrap (깊이 제한)
  5. 메타
       제품/차종/클레임번호, 발신·수신, 일자, 스레드 id
       PII 플래그, 내부메일 표시
       parser=docling|extract-msg|tika
  6. MCP
       get_email, list_attachments, get_thread
       첨부 조회는 해당 포맷 도구에 위임
```

원본 `.msg`와 분리한 본문·첨부는 둘 다 보관한다.

## 단계별 권장

### 1. 파싱: 본문은 Docling, 첨부는 직접 푼다

Outlook `.msg`는 `.doc`와 같은 OLE 컴파운드다. 파일 전체를 임베딩하지 않는다. **헤더·본문**은 Docling email 백엔드로 넣어도 된다.

- Docling: `mail-parser` extra. `EmailBackendOptions.list_attachments=true`면 첨부 **파일명**을 문서 끝에 붙인다. 바이너리는 절대 임베드하지 않는다
- Python: `extract-msg`. RTF 본문, named properties, Conversation-Index를 Docling보다 잘 남기는 경우가 있다
- 범용: Apache Tika (`application/vnd.ms-outlook`)
- 둘 다 실패하면 `failed_msg`로 남긴다. 빈 문서로 인덱싱하지 않는다

`from`, `to`, `cc`, `date`, `subject`는 청크가 아니라 **메타데이터**다. 본문과 섞으면 “누가 보냈는지”가 검색 노이즈가 된다.

### 2. 본문: 메일 1통 = RAG 문서 1개 (가족 A형)

메일 본문은 제목 계층이 거의 없다. HybridChunker보다 **메일 단위**가 맞다. 서술 텍스트이므로 가족 A처럼 임베딩한다. 첨부 xlsx/pdf를 본문에 붙이지 않는다.

- 긴 회신은 `-----Original Message-----` / `From:` 인용을 잘라 원문과 분리한다
- HTML만 있으면 태그 제거 후 텍스트. 서명·면책 문구는 본문 청크에서 뺀다
- RTF 본문만 있는 MSG는 extract-msg가 더 안전하다
- 본문이 비고 첨부만 있는 메일이 흔하다. 빈 본문을 임베딩하지 말고 첨부 쪽으로 안내한다

### 3. 첨부: 다시 포맷 라우터

시장품질 메일의 본체는 종종 첨부다. 100MB xlsx, 스캔 PDF, 클레임 사진.

- 첨부는 MSG 안에 묻지 말고 파일로 저장한다
- 경로·해시·파일명·content-id를 부모 메일에 연결한다
- 저장 후 20종 표로 **재입고**한다. 메일 파서와 Docling이 엑셀을 열지 않는다
- Docling이 첨부 이름을 나열해도 바이너리 fan-out을 생략하지 않는다
- 중첩 MSG/EML(전달)은 깊이 제한을 두고 재귀 unwrap 한다

### 4. 스레드

`In-Reply-To`, `References`, Outlook `Conversation-Index`로 conversation id를 만든다.

같은 클레임 메일 10통은 스레드로 묶는다. 최신 본문으로 답하고 첨부는 스레드 전체에서 모은다. 담당자 질문은 “그 메일”이 아니라 “그 이슈의 주고받은 내용”인 경우가 많다.

### 5. PII / 내부 메일

시장품질 메일에는 담당자 이름, 전화, 협력사 연락처, 내부 유통 문구가 기본이다.

- 업무 메일함만 넣는다. 개인 메일함 전체를 넣지 않는다
- 발신/수신은 필터용 메타로 둔다. 답변에 개인 연락처를 반복하지 않는다
- 외부 임베딩 API에 원문 MSG를 올리지 않는다

### 6. MCP

`search` 하나로 메일을 풀지 않는다.

1. `get_email(message_id)` — 헤더 + 본문 + 짧은 인용
2. `list_attachments(message_id)` — 파일명, 포맷, 크기, 하위 doc_id
3. `get_thread(conversation_id)` — 시간순 목록
4. 첨부 이후는 `get_section` / `query_tables` / `get_page_image`에 **위임**

Codex는 메일을 연 뒤 첨부 목록을 보고, xlsx면 SQL 도구로 넘어가게 한다.

## 흔한 실패

- MSG 바이너리를 텍스트로 디코딩해 OLE 잔해가 청크에 남음
- Docling이 본문을 읽었으니 첨부 fan-out을 생략함 → 클레임 엑셀/PDF가 사라짐
- `list_attachments` 파일명만 인덱싱하고 바이트는 버림
- 첨부 xlsx를 본문 하단에 붙여 Milvus에 넣음 → 건수 질문이 깨짐
- 스레드를 개별 메일 10개로 검색해 같은 답이 중복
- 중첩 .msg/.eml을 한 겹만 풀어 전달 첨부가 남음
- Tika 타임아웃으로 큰 첨부 MSG가 잘림
- 확장자 `.msg`인데 실제는 `.eml` 또는 암호 ZIP

## 하지 말 것

- MSG 전체(첨부 포함)를 하나의 임베딩 단위로 넣기
- 첨부를 버리고 제목+본문만 인덱싱하기
- Docling 첨부 이름 목록을 fan-out 대체로 쓰기
- 내부 메일을 웹 변환 API에 업로드하기
- 첨부 100MB xlsx를 메일 파서가 메모리에 펼치기

## 인접 포맷

- `.eml` → [12-eml.md](12-eml.md). 분기는 같고 파서만 MIME/Docling email
- 첨부 PDF → [01-pdf.md](01-pdf.md)
- 첨부 XLSX → [04-xlsx.md](04-xlsx.md). RAG 금지
- 첨부 PNG/JPEG → [17-png-jpeg.md](17-png-jpeg.md)
- `.doc`(OLE) → [03-doc.md](03-doc.md). 같은 OLE여도 메일이 아님
