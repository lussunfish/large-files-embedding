# Visio VSDX 권장 파이프라인

- 배경: 시장품질 공정흐름도·품질계통도·8D 로직이 Visio(`.vsdx`, 2013+)로 온다. 도면은 가족 H다. XML을 청크하지 않는다. Docling은 vsdx를 파싱하지 않는다.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

`.vsdx`는 ZIP+XML이다. 셰이프 텍스트와 페이지 렌더가 본체다. **일반 zip으로 풀지 않는다.** python `vsdx`(dave-howard/vsdx)로 페이지별 셰이프 텍스트를 뽑고, 페이지는 LibreOffice/Visio/PDF로 렌더한다. 커넥터 from–to는 가벼운 그래프로 선택한다. 태그 원문을 임베딩하지 않는다. Codex는 페이지 목록·이미지·도형 글자를 따로 본다.

| 선택 | 판단 |
|---|---|
| vsdx XML을 청크해 Milvus | 하지 말 것 |
| `vsdx`로 셰이프 텍스트 추출 | **기본 경로** |
| 페이지 → PNG 렌더 후 VLM | **기본 경로** |
| LangChain VsdxParser | 차선. ZIP XML dump. 셰이프 단위가 아님 |
| 커넥터 from–to 경량 그래프 | 선택. 흐름도가 본체일 때 |
| 일반 ZIP(30)으로 풀어 미디어만 | 하지 말 것 |
| Docling에 vsdx 직접 | 하지 말 것. 미지원 |
| 일반 XML(19)로 재파싱 | 하지 말 것 |
| 바이너리/ZIP을 한 청크 | 하지 말 것 |

권장 한 줄:

```
.vsdx → 시그니처(ZIP/XML) → 페이지 인벤토리
      → vsdx 라이브러리: 셰이프 텍스트 + (선택) 커넥터 그래프
      → 페이지 PNG (LibreOffice/Visio) 또는 PDF
      → VLM 캡션
      → MCP: list_pages / get_page_image / get_shape_text
```

## 권장 파이프라인

```
업로드 .vsdx
  1. 시그니처
       PK/ZIP + visio/pages. OLE면 34-vsd
       일반 XML/그림이면 재분류
  2. 페이지 인벤토리
       페이지명, 크기, 셰이프 수
       빈 배경 페이지는 메타만
  3. 텍스트
       vsdx.VisioFile: 페이지별 Shape.text
       Shape / Text / Field (품번, 공정명, 검사항목)
       마스터·스텐실 반복 라벨은 한 번만
       LangChain VsdxParser는 unzip XML. 기본이 아님
  4. 커넥터 (선택)
       from_id → to_id, 화살표 방향
       공정 흐름·계통도 Grain
  5. 렌더
       페이지 PNG (LibreOffice/Visio). PDF면 01
       VLM 한 줄: 흐름 종류, 분기, 핵심 박스
  6. 인덱싱
       셰이프 텍스트 + 캡션 → 검색
       XML 원문·바이너리 금지
  7. MCP
       list_pages, get_page_image, get_shape_text
  원본 .vsdx 와 페이지 PNG 를 둘 다 보관
```

## 단계별 권장

### 1. XML·ZIP을 문서처럼 자르지 않는다

vsdx는 pptx와 같이 ZIP이다. `visio/pages/pageN.xml`을 19번 파이프라인에 넣으면 네임스페이스·기하 태그만 쌓인다. 30-zip처럼 풀어 미디어만 흩뿌리면 도면이 깨진다.

- 파서는 셰이프 텍스트와 연결선만 본다
- `Cell`, `Geom`, 좌표 숫자는 본문 청크가 아니다
- 100MB급은 페이지 단위다. ZIP 전체를 본문처럼 펼치지 않는다

공정흐름도·품질계통도는 **그림 + 짧은 라벨**이다. Word 섹션 트리가 아니다.

### 2. 파서는 `vsdx`다

기본은 python `vsdx`(dave-howard/vsdx)다. 페이지를 돌며 셰이프 텍스트를 뽑는다.

```python
from vsdx import VisioFile

with VisioFile("flow.vsdx") as vis:
    for page in vis.pages:
        for shape in page.shapes:
            label = (shape.text or "").strip()
            # 라벨만 남긴다. XML 태그는 버린다
```

- LangChain `VsdxParser`는 ZIP을 풀어 페이지 XML 텍스트를 모은다. 셰이프 단위·커넥터가 아니다. 차선
- Docling은 vsdx를 파싱하지 않는다. StandardPdfPipeline에 확장자만 바꿔 넣지 않는다
- 그룹 도형은 자식 텍스트를 모은다
- 레이어 숨김 셰이프도 라벨이면 추출한다. 화면만 믿지 않는다
- 반복 스텐실 머리글은 메타로만

시장품질 Visio 박스에는 공정명, 품번, 검사항목, 불량모드가 들어 있다.

```text
[문서] 2024 OO 차종 품질계통도
[페이지] 2 / 도장 공정
[셰이프] 전처리 → 전착 → 중도
[캡션] 도장 라인 3단, 전착 후 중도로 분기
```

### 3. 커넥터는 선택 그래프

화살표가 본체인 흐름도만 그래프를 남긴다. 조직도·배치도는 텍스트+이미지면 충분하다. `vsdx`의 `Connect`를 쓴다.

- `(from_shape, to_shape, label)` 세 칼럼. 무거운 그래프 DB는 기본이 아니다
- 사이클·분기(OK/NG)는 캡션에 한 줄
- 그래프를 행처럼 SQL 팩트에 넣지 않는다. 가족 H이지 C가 아니다

### 4. 페이지 렌더 + VLM

텍스트만 모으면 좌우 분기·Swimlane이 사라진다.

- 페이지를 PNG로 렌더한다. LibreOffice 또는 Visio. 해상도는 읽기용, 원본 대체 아님
- PDF로 보낸 경우는 [01-pdf.md](01-pdf.md)의 도면 페이지 분기
- VLM: 차트 종류가 아니라 **흐름 한 줄** (시작, 핵심 공정, 분기)
- OCR은 셰이프 XML에 글자가 없을 때만 보조
- 인용은 `파일명 + 페이지명`. Codex는 이미지를 열어 확인한다

### 5. MCP

`search` 하나로 도면을 풀지 않는다.

1. `list_pages(doc_id)` — 페이지명, 셰이프 수
2. `get_shape_text(doc_id, page)` — 박스 라벨 목록
3. `get_page_image(doc_id, page)` — PNG. 흐름 확인

숫자는 라벨·캡션 근거와 같이 말한다. 계통도를 표로 착각해 `query_tables`로 보내지 않는다.

## 흔한 실패

- page XML을 코드펜스로 임베딩해 좌표만 검색됨
- LangChain VsdxParser dump를 본문으로 넣어 태그가 검색됨
- 텍스트만 모아 화살표 방향이 반대가 됨
- ZIP을 30-zip처럼 풀어 미디어만 가족 F로 흩뿌림
- 전 페이지를 한 청크에 붙여 공정이 섞임
- 렌더 없이 텍스트만 넣고 Swimlane 의미가 사라짐
- Docling이 Visio를 받는다고 입고 로그에 원본만 남기기

## 하지 말 것

- vsdx를 마크다운/XML dump 후 토큰 자르기
- 일반 zip/xml 파이프라인으로 우회
- Docling StandardPdfPipeline을 기본으로 쓰기
- 원본을 지우고 PNG만 남기기
- 커넥터 그래프를 클레임 SQL에 UNION
- 웹 변환 API에 사내 공정도 업로드
- MCP를 `search` 하나로 끝내기

## 인접 포맷

- `.vsd` → [34-vsd.md](34-vsd.md). OLE 변환 후 이 문서 또는 PDF
- 배포 PDF 도면 → [01-pdf.md](01-pdf.md). 페이지 이미지 분기
- 슬라이드 안의 흐름도 → [07-pptx.md](07-pptx.md). 가족 D
- 페이지 PNG만 온 경우 → [17-png-jpeg.md](17-png-jpeg.md). 가능하면 원본 vsdx를 찾는다
- CAD → 가족 H 형제. 여기 XML 파서를 재사용하지 말 것
