# .hwpx 권장 파이프라인

- 배경: 한글 2014+ 기본 저장 포맷 `.hwpx`를 시장품질 RAG/MCP에 넣을 때, 바이너리 HWP와 같은 경로로 취급하지 않는다.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

`.hwpx`는 가족 A다. **ZIP + XML (OWPML)** 이다. `.hwp` 바이너리보다 구조 접근이 쉽다. **Docling은 HWPX를 지원하지 않는다.** 압축을 풀어 섹션 XML을 읽거나, hwpkit / syhwp / jakal-hwpx로 문단·표를 뽑은 뒤 가족 A(섹션/table)로 매핑한다. 마크다운 dump를 청크 본체로 쓰지 않는다. Heading 충실도가 HybridChunker에 필요하면 한컴으로 DOCX 변환 후 [02-docx.md](02-docx.md)를 탄다. 미리보기 이미지만 있는 일반 ZIP으로 취급하지 않는다.

권장 한 줄:

```
.hwpx (원본 보관)
  → 시그니처(ZIP) + Contents/*.xml 확인
  → 구조 추출: unzip OWPML 또는 hwpkit / syhwp / jakal-hwpx
  → 문단·표를 가족 A JSON으로 매핑 (마크다운 dump 금지)
  → Heading 충실도가 필요하면 한컴 → DOCX → 02-docx
  → 도장·양식이 본이면 PDF → 01-pdf
```

| 선택 | 판단 |
|---|---|
| `.hwp` 바이너리 파서(pyhwp)에 넣기 | 하지 말 것. 포맷이 다름 |
| ZIP으로만 풀어 미리보기 이미지 임베딩 | 하지 말 것 |
| unzip OWPML / hwpkit / syhwp / jakal-hwpx 후 구조 매핑 | **기본 경로** (Linux/CI) |
| 한컴 → DOCX 후 HybridChunker | Heading 충실도가 필요할 때 |
| Docling에 hwpx 직접 투입 | 하지 말 것. 네이티브 지원 없음 |
| Markdown dump 후 토큰 자르기 | 하지 말 것 |
| 변환본만 남기고 원본 삭제 | 하지 말 것 |

## 권장 파이프라인

```
업로드 .hwpx
  1. 시그니처
       PK ZIP + Contents/section*.xml  → hwpx
       HWP 바이너리                    → 09-hwp
  2. 구조 확인
       Contents/header.xml, sectionN.xml
       BinData/ (그림)
       Preview/ 는 썸네일일 뿐, 본문이 아님
  3. 추출 경로 선택
       a. unzip OWPML: 문단·표·제목 스타일 → 가족 A 매핑
       b. hwpkit / syhwp / jakal-hwpx: 같은 매핑, 파서만 교체
       c. 한컴 변환 → DOCX (Heading 충실도 우선)
       d. LibreOffice (필터 있을 때, 검증 필수)
  4. 도착
       서술·표 → 02-docx 또는 동등 가족 A JSON
       도장·스캔 → 01-pdf (가족 B)
  5. 그림
       BinData 저장 + 캡션 / VLM
  원본 .hwpx 보관
```

## 단계별 권장

### 1. HWP와 어디가 다른가

- `.hwp` = 한컴 바이너리. Docling 미지원. 외부 파서가 약했다.
- `.hwpx` = OOXML과 비슷한 패키지. `mimetype`, `Contents/`, `BinData/`, `Preview/`. OWPML.

섹션 XML에 문단, 표, 스타일이 있다. 제목 계층을 살리면 HybridChunker가 동작한다. 다만 한컴 전용 스타일·글상자·차트는 XML만으로 부족할 수 있다. 그때는 한글 → DOCX가 맞다.

확장자가 `.hwp`인데 ZIP이면 이 문서로 보낸다. pyhwp는 HWPX를 읽지 못한다.

### 2. XML을 직접 읽을 때

unzip OWPML은 유효한 경로다. 라이브러리 없이도 섹션을 연다.

- `Contents/section*.xml`을 순서대로 읽는다.
- 문단 스타일(개요 수준)을 Heading으로 매핑한다.
- 표는 셀 텍스트를 table 객체로 유지한다. 본문 문장에 섞지 않는다.
- `BinData/` 이미지는 따로 저장한다. `Preview/PrvImage`는 표지가 아니다.
- 배포용 암호 ZIP이면 입고에서 실패로 남긴다. 비밀번호를 파이프라인에 하드코딩하지 않는다.

라이브러리를 쓸 때:

- **hwpkit** — 순수 Python, hwp+hwpx 한 API
- **syhwp** — MIT, 텍스트/표/Markdown/HTML. Markdown은 검수용이고 청크 본체가 아니다
- **jakal-hwpx** — hwp+hwpx 읽기/쓰기. 구조 편집이 필요할 때

자체 XML 파서는 사내 양식이 고정일 때 이득이다. 양식이 제각각이면 한컴 → DOCX가 더 싸다.

### 3. 변환 후 가족 A

구조 추출 결과를 **가족 A**로 올린다. 문단은 섹션, 표는 `type=table`. 마크다운 문자열을 HybridChunker에 넣지 않는다.

Heading 경로(`1. 현상 > 1.1 …`)가 약하면 한컴 공식 변환 → DOCX가 우선이다. HybridChunker는 Word 스타일 트리에 기대는 부분이 크다. LibreOffice는 필터가 있을 때만, 그리고 표 개수 검증을 전제로 쓴다.

도착 `.docx`는 `02-docx.md`와 같다.

- Docling SimplePipeline JSON
- HybridChunker + heading breadcrumb
- 표는 type=table
- MCP: `get_outline`, `get_section`, `get_table`

도장·직인·스캔 첨부면 PDF로 보내 `01-pdf.md`를 탄다.

### 4. 이미지와 차트

품질 HWPX에는 공정 사진, Pareto 캡처, 스탬프가 많다.

- XML 본문에 숫자가 없으면 VLM 캡션을 붙인다.
- 차트 OLE는 변환 과정에서 그림이 된다. 07과 같이 bar/pie/line은 chart understanding, 사진은 VLM.
- ZIP 안의 모든 바이너리를 페이지로 임베딩하지 않는다.

## 흔한 실패

- `.hwpx`를 `.hwp` 바이너리 경로(pyhwp)에 넣어 실패한다.
- Docling이 한글을 받는다고 확장자만 바꿔 넣는다.
- `Preview/` 썸네일만 OCR해 본문을 버렸다고 본다.
- ZIP을 일반 첨부 컨테이너로 풀어 이미지를 가족 F로 흩뿌린다.
- 섹션 XML·syhwp Markdown을 태그 제거 텍스트로만 dump 해 표가 붕괴한다.
- Heading이 죽은 채 HybridChunker를 돌려 8D 섹션이 한 덩어리가 된다.

## 하지 말 것

- 일반 ZIP·이미지 묶음으로 취급
- antiword 식 텍스트 추출
- Markdown dump 후 토큰 자르기
- 원본 삭제
- 외부 웹 변환에 사내 문서 업로드
- 변환 실패를 빈 문서로 인덱싱

`.hwpx`는 “압축을 풀 수 있는 한글 문서”다. 풀고 나서도 문서 파이프라인(가족 A)을 탄다.

## 인접 포맷

- `.hwp` → [09-hwp.md](09-hwp.md). 바이너리 선행 포맷. 변환기 우선순위가 더 중요하다.
- `.docx` → [02-docx.md](02-docx.md). Heading 충실도가 필요할 때의 도착점.
- `.pdf` → [01-pdf.md](01-pdf.md). 레이아웃·도장일 때.
- `.xml` → [19-xml.md](19-xml.md). 스키마 있는 정형 XML과 한글 섹션 XML은 다르다.
- `.cell` / `.show` → [37-cell.md](37-cell.md), [38-show.md](38-show.md). 한컴 패밀리. Docling 미지원.
