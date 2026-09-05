# .hwp 권장 파이프라인

- 배경: 한국 제조 시장품질 업무에서 `.hwp`(한글)는 8D·대책서·공문의 핵심 포맷이다. Docling 단일 경로로 넣지 않는다.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

`.hwp`는 한컴 한글의 **바이너리**다. ZIP/XML이 아니다. **Docling은 HWP를 지원하지 않는다.** 우선 한글로 구조 보존 변환하고, Linux/CI에서는 hwpkit·syhwp로 본문·표를 뽑는다. 도착은 가족 A(DOCX) 또는 필요 시 가족 B(PDF)다. 텍스트만 긁는 antiword 식 추출은 쓰지 않는다. pyhwp를 유일한 폴백으로 두지 않는다. 법무·품질 원본은 반드시 보관한다. 후속 포맷은 `.hwpx`다.

권장 한 줄:

```
.hwp (원본 보관)
  → 시그니처 확인
  → (1) 한컴 공식/COM (있으면)
  → (2) hwpkit 또는 syhwp — Linux/CI에서 본문+표
  → (3) HWP→HWPX 후 10-hwpx
  → (4) LibreOffice HWP 필터 — 자주 불완전
  → (5) pyhwp 최후, AGPL 주의
  → 제목·표가 중요하면 DOCX → 02-docx
  → 도장·레이아웃이 중요하면 PDF → 01-pdf
```

| 선택 | 판단 |
|---|---|
| Docling에 `.hwp` 직접 투입 | 하지 말 것. 네이티브 지원 없음 |
| 한컴 공식 변환 → DOCX | **기본 경로** (Windows/한컴 있을 때) |
| hwpkit / syhwp 구조 추출 | Linux/CI 기본. 본문+표 |
| HWP→HWPX 후 10-hwpx | 한컴 무료 변환기(배치 30) 또는 동등 경로 |
| LibreOffice HWP 필터 → DOCX | 차선. 표·머리글이 자주 깨진다 |
| hwp5 / pyhwp 텍스트 추출 | **최후** 폴백. AGPL. HWPX 없음. 2020 이후 정체 |
| antiword·catdoc 식 dump | 하지 말 것 |
| 변환본만 남기고 원본 삭제 | 하지 말 것. 품질·증적 문서 |

한컴 공식 블로그(2026-07)가 적는 오픈소스는 pyhwp, hwplib/hwpxlib(Java), hwp.js다. 그 목록만 따르면 Python 경로가 낡는다. 더 새 Python은 hwpkit(순수 Python, hwp+hwpx), syhwp(MIT, 텍스트/표/md/html), jakal-hwpx(hwp+hwpx 읽기/쓰기)다.

## 권장 파이프라인

```
업로드 .hwp
  1. 시그니처
       HWP 5.x 바이너리  → 이 문서
       ZIP (PK)          → 확장자만 잘못된 .hwpx → 10-hwpx
       OLE/한글 3.0      → 별도 레거시. 한컴만 안정
  2. 변환기 선택 (위에서 아래로)
       한컴오피스 자동화 / 공식 변환
       hwpkit 또는 syhwp (본문+표, Linux/CI)
       한컴 무료 HWP→HWPX (배치 30) 후 10-hwpx
       LibreOffice + HWP import 필터 (있으면, 검증 필수)
       pyhwp 텍스트 (최후, AGPL)
  3. 도착 포맷
       제목·표·리스트     → .docx → 02-docx (가족 A)
       구조 추출만 되면   → 섹션/표를 가족 A JSON으로 매핑
       도장·스캔·양식     → .pdf  → 01-pdf (가족 B)
  4. 검증
       한글 깨짐, 표 개수, Heading 잔존
  5. 메타
       converted_from=hwp, converter=hancom|hwpkit|syhwp|hwpx|libreoffice|pyhwp
  원본 .hwp 보관
```

## 단계별 권장

### 1. 왜 Docling에 바로 넣지 않는가

HWP 5.x는 한컴 전용 바이너리다. 제목 스타일, 표, 각주, 머리글이 XML로 열려 있지 않다. Docling은 HWP/HWPX를 파싱하지 않는다. JSON을 기대하고 넣으면 빈 문서나 깨진 문단이 나온다. 파서는 변환기이고, 파싱은 변환 이후다.

후속 포맷 `.hwpx`는 ZIP+XML이다. 2014 이후 한글이 저장한 파일은 확장자가 `.hwp`여도 실제로는 `.hwpx`일 수 있다. 첫 단계는 변환이 아니라 **시그니처**다.

### 2. 변환기 우선순위

1. **한컴 공식 변환 / 한컴오피스 자동화**  
   Windows에 한글이 있으면 COM·배치 변환이 표와 스타일을 가장 잘 살린다. 사내 변환 서버가 있으면 그걸 재사용한다. Heading 충실도가 HybridChunker에 필요하면 DOCX로 보낸다.
2. **hwpkit 또는 syhwp**  
   Linux/CI에서 한컴이 없을 때의 본문+표 경로다. 둘 다 순수 Python이고 HWP와 HWPX를 같이 읽는다. syhwp는 MIT, 텍스트/표/Markdown/HTML. hwpkit도 순수 Python. 마크다운 dump를 청크 본체로 쓰지 말고, 문단·표를 가족 A 구조(섹션/table 객체)로 매핑한다.
3. **HWP → HWPX 후 [10-hwpx.md](10-hwpx.md)**  
   한컴이 무료 HWP→HWPX 변환기를 제공한다. 한 번에 30개. 변환되면 OWPML이라 구조 추출이 쉽다. jakal-hwpx도 hwp+hwpx 읽기/쓰기가 된다. 도착은 10이다.
4. **LibreOffice HWP 필터**  
   필터가 설치된 환경에서만 시도한다. 없는 이미지가 많다. 있어도 병합 표, 글상자, 머리글 품번이 빠지는 경우가 많다. 성공해도 표 개수를 원본과 비교한다. **자주 불완전하다.**
5. **pyhwp (hwp5)**  
   **최후** 폴백이다. 2020-05 이후 정체(0.1b15), HWPX 미지원, 변환은 experimental, **AGPL-3.0**. SaaS·사내 배포에 라이선스를 먼저 본다. HybridChunker 입력의 본체로 쓰지 않는다. 검색 힌트·실패 파일 분류용이다.

Java가 허용되면 hwplib/hwpxlib(Apache 2.0)도 읽기/쓰기가 된다. 프론트 미리보기만 hwp.js다. 웹 변환 API에 사내 8D를 올리지 않는다.

### 3. DOCX로 갈지, PDF로 갈지

시장품질 HWP는 대개 조사서·8D·시정조치·공문이다.

- **구조가 본이면 DOCX.** 제목 1/2, 표, 리스트를 살린 뒤 `02-docx.md`의 SimplePipeline → HybridChunker → Milvus.
- **한컴 없이 본문+표만 필요하면** hwpkit/syhwp 추출을 가족 A JSON에 직접 매핑한다. Heading이 약하면 한컴 DOCX가 다시 맞다.
- **도장, 서명, 스캔 첨부, 고정 양식이 본이면 PDF.** `01-pdf.md`. 비전/OCR 분기를 탄다.

둘 다 기본으로 돌리지 않는다. 표가 많은 대책서는 DOCX가 맞다.

### 4. 검증과 메타

- 한글 깨짐 (`□`, 모지바케)이면 폰트/변환기 문제다. 인덱싱하지 않는다.
- 표 개수, Heading 유무를 변환 전후에 비교한다.
- `source_path`, `converted_from=hwp`, 변환기를 남긴다. 나중에 한컴 경로를 붙여도 재처리할 수 있다.

MCP는 도착 포맷을 따른다. DOCX면 `get_outline` / `get_section`, PDF면 페이지 도구다. `search` 하나가 아니다.

## 흔한 실패

- Docling이 “문서를 받는다”고 HWP를 PDF 파이프라인에 넣는다.
- pyhwp만 폴백으로 두어 Linux/CI에서 표가 죽거나 AGPL을 놓친다.
- hwpkit/syhwp Markdown dump를 토큰 잘라 임베딩해 표 숫자가 문장으로 흩어진다.
- LibreOffice 필터 없는 컨테이너에서 변환 “성공” 로그가 난다. 실제로는 빈 파일이다.
- `.hwpx`를 `.hwp` 바이너리 경로에 넣어 ZIP을 깨뜨린다.
- 원본을 지워 감사·재처리가 불가능하다.

## 하지 말 것

- antiword / catdoc / 임의 바이너리 strings로 본문 추출
- 마크다운 dump 후 토큰 자르기
- pyhwp를 유일한 Python 경로로 고정
- 변환 실패를 빈 문서로 인덱싱
- 원본 삭제
- 사내 품질 문서를 외부 변환 웹에 업로드

## 인접 포맷

- `.hwpx` → [10-hwpx.md](10-hwpx.md). ZIP+XML 후속. 이 문서보다 파싱 여지가 크다.
- 변환 후 `.docx` → [02-docx.md](02-docx.md). 가족 A 본체.
- 변환 후 `.pdf` → [01-pdf.md](01-pdf.md). 도장·스캔일 때.
- `.doc` → [03-doc.md](03-doc.md). 같은 “레거시 → 현대 포맷” 게이트. 포맷은 다르다.
- `.cell` / `.show` → [37-cell.md](37-cell.md), [38-show.md](38-show.md). 같은 한컴 우선. Docling 미지원.
