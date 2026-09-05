# .odp 권장 파이프라인

- 배경: 시장품질 월간보고·8D 요약·협력사 품질회의 자료가 LibreOffice Impress `.odp`로 올 때 슬라이드 단위를 유지한다.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

`.odp`는 가족 D다. ODF 프레젠테이션이지 Word 섹션 트리가 아니다. **슬라이드 1장 = 청크 1개**가 기본 단위다. **Docling `OdpDocumentBackend`(odfdo)가 1순위**다. 슬라이드 경계·노트·표가 남으면 변환하지 않는다. 약하거나 실패하면 LibreOffice로 `.pptx`로 바꾼 뒤 [07-pptx.md](07-pptx.md)를 탄다. 전 슬라이드를 하나의 텍스트 덩어리로 평탄화하지 않는다.

권장 한 줄:

```
.odp → 시그니처(ZIP + ODF mimetype) 확인
     → Docling OdpDocumentBackend (odfdo)  ← 1순위
     → (실패·노트/표 손실 시) LibreOffice → .pptx → 07-pptx
     → 슬라이드 단위 청크(제목+본문+노트+차트캡션)
     → 표는 table 객체
     → bar/pie/line: Docling chart extraction, 사진·공정: VLM
     → Milvus (slide_index 필터)
     → MCP: list_slides / get_slide(n)
```

| 선택 | 판단 |
|---|---|
| 전 슬라이드를 한 blob으로 dump | 하지 말 것. 이슈가 섞인다 |
| content.xml 텍스트만 긁기 | 하지 말 것. 페이지 경계가 사라진다 |
| Docling OdpDocumentBackend 직접 파싱 | **기본 경로** |
| LibreOffice → `.pptx` 후 07 | 폴백. 백엔드가 약할 때만 |
| PDF로 변환 후 StandardPdfPipeline | 기본 경로 아님. 시각 검색이 필요할 때만 |
| 차트 이미지를 무시하고 본문만 | 하지 말 것. 월보는 차트가 본체 |
| 일반 ZIP으로 풀어 그림만 임베딩 | 하지 말 것 |

## 권장 파이프라인

```
업로드 .odp
  1. 포맷 검증
       ZIP + mimetype=application/vnd.oasis.opendocument.presentation
       OOXML이면 확장자만 잘못된 .pptx → 07
       OLE이면 .ppt → 08
  2. 파싱 경로 선택
       a. Docling OdpDocumentBackend (odfdo)  ← 먼저
          슬라이드/노트/표가 남으면 그대로
       b. 실패·손실이면 soffice --headless --convert-to pptx
          UserInstallation + timeout + 한글 폰트, 원본 보관
  3. 슬라이드 조립 (1장 = 1청크)
       [제목]
       [본문 불릿]
       [발표자 노트]
       [표 직렬화]
       [차트 표 또는 VLM 캡션]
  4. 메타데이터
       제품, 차종, 문서유형, 기간, slide_index, 슬라이드 제목
       converted_from=odp (변환한 경우)
  5. 인덱싱
       슬라이드 청크 → Milvus (하이브리드 + slide_index)
       표 청크는 type=table 로 분리
  6. MCP
       list_slides, get_slide(n), search_passages, get_table
  원본 .odp 와 파싱 JSON(또는 변환 .pptx)을 둘 다 보관
```

## 단계별 권장

### 1. 확장자가 아니라 ODF 시그니처

협력사·해외 벤더는 `.odp`인데 실제로는 `.pptx`이거나, 반대로 `.pptx`인데 ODF인 파일이 있다.

- `PK` ZIP + `mimetype` 파트가 `opendocument.presentation` → 진짜 `.odp`
- `[Content_Types].xml` + `ppt/slides` → [07-pptx.md](07-pptx.md)
- OLE CFB (`D0 CF 11 E0`) → [08-ppt.md](08-ppt.md)
- 일반 자료 ZIP이면 [30-zip.md](30-zip.md)

`content.xml`의 `draw:page`가 슬라이드다. ZIP만 풀어 텍스트 노드를 이어 붙이면 장 경계가 사라진다.

### 2. Docling ODP가 1순위, 변환은 폴백

Docling은 ODF 프레젠테이션을 네이티브로 읽는다. 백엔드는 `OdpDocumentBackend`, 구현은 `odfdo`다. PPTX처럼 슬라이드 단위 DoclingDocument가 나오면 변환하지 않는다.

표본에서 슬라이드 수·한글·노트가 어긋나면 LibreOffice → `.pptx`를 폴백으로 고정한다. 그때 soffice를 숨기지 않는다.

```bash
soffice --headless --norestore --nolockcheck \
  -env:UserInstallation=file:///tmp/lo-profile-$JOB \
  --convert-to pptx:"Impress MS PowerPoint 2007 XML" \
  --outdir /data/normalized \
  monthly_review.odp
```

운영에서 지킬 것 (폴백 변환):

- 컨테이너에 `fonts-noto-cjk` / `fonts-nanum`을 넣는다. 없으면 품번·고장모드가 `□□`가 된다.
- LibreOffice는 동시 실행에 약하다. 워커 하나, 또는 파일마다 별도 `UserInstallation`.
- 타임아웃을 건다. 깨진 ODP가 soffice를 붙잡는다. issue #3819와 같다.
- 변환 실패는 배치를 멈추지 않고 `failed_odp`로 남긴다.
- 100MB급 임베디드 그림 덱은 변환 메모리를 제한한다.

변환본은 파생물이다. 원본 `.odp`는 삭제하지 않는다.

### 3. 청크: 슬라이드를 평탄화하지 말 것

시장품질 덱은 한 장이 한 이슈인 경우가 많다. `현상 / 원인 / 대책 / 일정`이 연속 슬라이드다. 전 장을 이어 붙이면 “A품번 대책”이 “B품번 현상”과 같은 청크에 들어간다.

```text
[문서] 2024-09 OO 차종 시장품질 월간보고
[슬라이드] 12 / 원인분석 — 누유
[본문] ...
[노트] ...
[차트] Pareto: 누유 42%, 이음 21% ...
```

한 장이 임베딩 한도를 넘으면 같은 `slide_index` 안에서 본문/노트/표를 나눈다. 다른 슬라이드와 합치지 않는다. 마스터의 반복 머리글·바닥글은 메타로만 남긴다.

### 4. 표·차트와 MCP

- 슬라이드 표는 `TableItem`으로 남긴다. CSV/Markdown으로 직렬화하되 헤더를 유지한다.
- bar/pie/line은 Docling chart understanding enrichment(그림 → 표). 사진·공정 이미지는 VLM. 07과 같다.
- ODF 차트 XML에 시리즈가 있어도 렌더 결과와 다를 수 있다. 숫자는 표로 남기고, 시각 관계는 캡션으로 보완한다.
- Codex는 목차처럼 슬라이드 목록을 보고 해당 장만 읽는다.

1. `list_slides(doc_id)` — 번호, 제목, 차트 여부
2. `get_slide(doc_id, n)` — 본문+노트+표+캡션
3. `search_passages(query, filters)` — `slide_index` 필터
4. `get_table(doc_id, slide_index, table_id)`

인용은 `파일명 + 슬라이드 n`이다. PDF 변환은 비전 검색이 필요할 때만. 그때는 [01-pdf.md](01-pdf.md).

## 흔한 실패

- `content.xml`을 한 문자열로 붙여 품번·대책이 교차한다.
- Docling ODP를 건너뛰고 모든 파일을 pptx로 변환해 노트·마스터가 죽는다.
- Docling ODP가 노트를 버려도 검증 없이 인덱싱한다.
- 한글 폰트 없이 폴백 변환해 고장모드가 `□□`가 된다.
- 차트 이미지를 스킵해 Pareto 숫자가 없다.
- `.odp`를 일반 ZIP으로 풀어 `Pictures/`만 가족 F로 흩뿌린다.
- 확장자만 보고 OOXML `.pptx`를 ODF 파서에 넣는다.

## 하지 말 것

- 슬라이드 경계를 버리고 마크다운 dump 후 토큰 윈도우로 자르기
- `.odp → PDF → StandardPdfPipeline`을 기본으로 쓰기
- 웹 변환 API에 사내 품질 덱 업로드
- 변환 실패 파일을 빈 슬라이드로 인덱싱
- 원본을 지우고 변환 `.pptx`만 남기기
- MCP를 `search` 하나로 끝내기

## 인접 포맷

- `.pptx` → [07-pptx.md](07-pptx.md). 폴백 변환의 도착점.
- `.ppt` → [08-ppt.md](08-ppt.md). 같은 LibreOffice 게이트, 출발이 OLE. Docling은 soffice가 있어야 한다.
- `.pptm` → [28-pptm.md](28-pptm.md). 매크로 슬라이드. VBA는 버리고 07.
- `.odt` → [25-odt.md](25-odt.md). 같은 ODF지만 가족 A.
- `.ods` → [24-ods.md](24-ods.md). 같은 ODF지만 가족 C. RAG 금지.
- 한쇼 `.show` → [38-show.md](38-show.md). Docling이 파싱하지 않는다. 변환 후 같은 가족 D.
- 배포 PDF 덱 → [01-pdf.md](01-pdf.md). 슬라이드 경계가 페이지다.
