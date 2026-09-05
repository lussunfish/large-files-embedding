# .zip 권장 파이프라인

- 배경: 시장품질 월간 팩·8D 증적·협력사 회신이 하나의 `.zip`으로 올 때, 압축 파일을 문서로 임베딩하지 않고 엔트리마다 포맷 라우터로 재입고한다.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

`.zip`은 가족 G다. 서술 문서가 아니라 **컨테이너**다. 엔트리를 나열하고, `__MACOSX`를 건너뛰고, zip slip·압축 폭탄을 걸러낸 뒤 각 파일을 시그니처로 다시 보낸다. 암호 ZIP은 풀지 않고 실패 큐로 보낸다. ZIP 전체를 하나의 blob으로 임베딩하지 않는다. 누구나 쓸 수 있는 경로에 풀지 않는다.

Docling은 ZIP을 문서 컨테이너로 받지 않는다. 예외는 DocLang 아카이브 `.dclx`뿐이다. 일반 `.zip`을 Docling에 넣지 않는다.

권장 한 줄:

```
.zip → 시그니처(PK) + 엔트리 목록
     → 경로 정규화(zip slip) / 크기 폭탄 / __MACOSX 스킵
     → 파일마다 포맷 라우터 (xlsx→04, pdf→01, pptx→07, …)
     → 중첩 zip은 깊이 제한
     → 암호 zip → failed_encrypted
     → MCP: list_entries 후 하위 포맷 도구에 위임
```

| 선택 | 판단 |
|---|---|
| ZIP 바이너리/파일명 목록을 한 청크로 임베딩 | 하지 말 것 |
| 엔트리 검사 후 포맷 라우터 재입고 | **기본 경로** |
| 암호 ZIP 무차별 대입 | 하지 말 것. 실패 큐 |
| `/tmp` 777, 공유 업로드 디렉터리에 해제 | 하지 말 것 |
| 중첩 ZIP 무제한 재귀 | 하지 말 것. 깊이 제한 |
| Docling에 일반 ZIP 직접 투입 | 하지 말 것. `.dclx`만 예외 |
| 안을 무시하고 압축 파일만 메타 저장 | 하지 말 것. 본문이 안에 있다 |

## 권장 파이프라인

```
업로드 .zip
  1. 시그니처
       PK ZIP이 아니면 재분류
       OOXML(docx/xlsx/pptx/hwpx) / ODF / JAR 위장 확인
  2. 목록만 먼저 읽기 (해제 전)
       파일명, 압축 크기, 비압축 크기, 암호 플래그
       __MACOSX/, .DS_Store, Thumbs.db, ._ 리소스포크 스킵
  3. 안전 검사
       경로에 .., 절대경로, 드라이브 문자 → 거부 (zip slip)
       비압축 합 / 압축비 / 엔트리 수 / 단일 파일 상한
       100MB 입력이 GB로 펴지지 않게
  4. 해제
       전용 디렉터리 (0700), 심볼릭 링크 금지
       공용 쓰기 경로·원본 트리 위 직접 해제 금지
  5. 엔트리 fan-out (시그니처로 라우터)
       pdf          → 01-pdf
       docx / docm  → 02 / 27
       doc          → 03
       xlsx / xlsm / xls / csv → 04 / 21 / 05 / 06  (RAG 금지)
       pptx / pptm / ppt / odp → 07 / 28 / 08 / 26
       html / mht   → 13 / 29
       png/jpeg     → 17
       tiff         → 18
       msg / eml    → 11 / 12
       zip / 7z     → 재귀, depth+1
  6. 메타
       parent_zip_id, entry_path, 제품/차종/기간
  7. MCP
       list_entries, get_entry → 하위 get_section / get_slide / query_tables
```

원본 `.zip`과 해제 산출물을 둘 다 보관한다. 해제한 뒤 원본을 지우지 않는다.

## 단계별 권장

### 1. ZIP인지, 문서 패키지인지

OOXML·ODF·HWPX도 ZIP이다. 확장자 `.zip`이어도 안이 `word/document.xml`이면 [02-docx.md](02-docx.md)이고, `ppt/slides`면 [07-pptx.md](07-pptx.md), `mimetype`이 ODF면 24/25/26이다. 자료 아카이브만 이 문서를 탄다.

`.dclx`(DocLang archive)는 Docling 산출 묶음이다. 일반 월간 팩 ZIP이 아니다. 확장자·내부 구조로 가리고, 여기 아카이브 게이트에 섞지 않는다.

반대로 `.docx`로 왔지만 안이 여러 pdf/xlsx면 여기로 재분류한다. 확장자를 믿지 않는다.

### 2. 목록 → 검사 → 해제

시장품질 월간 팩은 100MB ZIP 안에 PDF 월보, xlsx 원장, pptx 덱, 클레임 사진이 섞인다. 압축 파일을 한 문서로 넣으면 검색이 파일명만 남는다.

해제 전에 막을 것:

- **zip slip**: `../`, `/etc/passwd`, `C:\`, 백슬래시 혼용. `normpath` 후 루트 밖으로 나가면 해당 엔트리만 거부한다
- **압축 폭탄**: 비압축 총량, 압축비, 엔트리 수, 파일당 상한. 입력 100MB라도 펴지면 수 GB가 된다
- **OS 쓰레기**: `__MACOSX/`, `.DS_Store`, `Thumbs.db`, `._파일명`
- **심볼릭 링크·디바이스 엔트리**: 따라가지 않는다
- **암호**: `flag_bits` 또는 읽기 실패 → `failed_encrypted`. 비밀번호를 추측하지 않는다. 담당자에게 평문 재제출을 요청한다

해제는 문서별 작업 디렉터리에만 한다. 모드는 `0700`. 웹 루트, `/tmp` 공용, NFS 공용 쓰기 경로에 풀지 않는다. 파일명 인코딩은 CP437/CP949/UTF-8 플래그를 본다. 한글 경로가 깨지면 엔트리 인덱스로 저장한다.

### 3. 엔트리마다 포맷 라우터

ZIP 파서가 엑셀을 열거나 PDF를 임베딩하지 않는다. 저장한 바이트를 20종(+추가) 표로 **재입고**한다.

- xlsx/xls/csv는 가족 C. 행을 Milvus에 넣지 않는다 ([04-xlsx.md](04-xlsx.md))
- pdf는 [01-pdf.md](01-pdf.md), 슬라이드는 07/26/28
- 메일 MSG/EML은 다시 첨부를 푼다. 깊이 카운트를 공유한다
- 중첩 ZIP은 `depth <= 2`(또는 3)에서 끊고 `failed_zip_depth`로 남긴다
- 같은 파일이 반복되면 해시로 합친다. 월간 팩의 중복 성적서가 흔하다

자식 문서에 `parent_id`, `entry_path`를 남긴다. Codex가 “그 ZIP 안의 3번 엑셀”을 물을 수 있어야 한다.

### 4. MCP

`search`에 ZIP 원문을 넣지 않는다.

1. `list_entries(zip_id)` — 경로, 포맷, 크기, 하위 doc_id, 스킵/실패 이유
2. `get_entry(zip_id, path)` — 메타 + 해당 포맷 도구로 위임
3. 이후는 `get_section` / `get_slide` / `query_tables` / `get_page_image`

Codex는 목록을 본 다음 xlsx면 SQL, pdf면 페이지, pptx면 슬라이드로 넘어가게 한다. 100MB 원장을 압축 해제 버퍼에 통째로 올리지 않는다.

## 흔한 실패

- ZIP 파일명을 임베딩해 “2024-09 월보.zip”만 검색되고 본문이 없다.
- 일반 `.zip`을 Docling에 넣어 빈 문서가 된다.
- `../` 엔트리가 워커 코드 위에 풀린다 (zip slip).
- 100MB 입력이 10GB로 펴져 디스크가 찬다.
- `__MACOSX` AppleDouble이 이미지/문서로 입고된다.
- 암호 ZIP을 빈 문서로 인덱싱한다.
- 중첩 ZIP을 무한 재귀한다.
- 안의 xlsx를 텍스트로 붙여 Milvus에 넣는다.

## 하지 말 것

- ZIP 전체를 하나의 임베딩 단위로 넣기
- 일반 `.zip`을 Docling 문서 입력으로 넣기 (`.dclx` 제외)
- 누구나 쓸 수 있는 경로·공유 `/tmp`에 해제
- 암호 ZIP 크랙
- 엔트리 확장자만 믿고 시그니처를 생략
- 자식 xlsx를 RAG 청크로 강등
- 원본 ZIP 삭제
- 하위 도구 없이 `search` 하나로 아카이브를 풀기

`.zip`은 MSG와 같은 컨테이너다. 풀고, 검사하고, 다시 이 표로 보낸다.

## 인접 포맷

- `.msg` / `.eml` → [11-msg.md](11-msg.md), [12-eml.md](12-eml.md). 같은 가족 G. 첨부 fan-out.
- `.mht` → [29-mht.md](29-mht.md). MIME 컨테이너. ZIP이 아니다.
- 내부 PDF → [01-pdf.md](01-pdf.md)
- 내부 XLSX → [04-xlsx.md](04-xlsx.md). RAG 금지
- 내부 PPTX → [07-pptx.md](07-pptx.md)
- 내부 DOCX → [02-docx.md](02-docx.md)
- `.hwpx` → [10-hwpx.md](10-hwpx.md). ZIP이지만 문서 패키지. 아카이브로 흩뿌리지 않는다.
