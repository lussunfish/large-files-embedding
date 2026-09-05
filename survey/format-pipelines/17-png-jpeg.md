# PNG/JPEG 권장 파이프라인

- 배경: 시장품질 RAG/MCP에서 PNG/JPEG를 어떻게 넣을 것인가. 가족 F
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

품질 문서의 그림은 일반 사진이 아니다. **보고서 안 차트/사진**과 **페이지 스캔**을 먼저 나눈다. CLIP 범용 사진 임베딩과 Docling-as-docx(SimplePipeline)는 쓰지 않는다.

Docling은 2026-09 기준 PNG/JPEG/TIFF/BMP/WEBP를 이미지 파이프라인 입력으로 받는다. **전체 페이지 스캔은 Docling 이미지/PDF OCR이 기본**이다. 차트처럼 OCR 텍스트가 없는 그림만 VLM을 쓴다. OCR 엔진은 RapidOCR `korean`(품번·한글 라벨).

| 선택 | 판단 |
|---|---|
| CLIP 등으로 일반 사진 임베딩 | 하지 말 것. 품질 문서에 부적합 |
| (a) 보고서 내부 차트/사진: VLM 캡션 + OCR 숫자, 부모 문서에 부착 | **차트·삽입 그림 기본** |
| (b) 촬영·스캔 전체 페이지: Docling 이미지/PDF OCR (RapidOCR korean) | **스캔 기본**. 선택 ColPali |
| 스캔을 커스텀 VLM만으로 처리 | 기본 아님. OCR이 기본, VLM은 OCR 텍스트가 없을 때 |
| Docling을 docx처럼 SimplePipeline 적용 | 하지 말 것 |
| EXIF를 문서 일자로 사용 | 거의 무효. 쓰지 않음 |
| 엑셀 화면 JPEG: OCR 표 + 저신뢰 플래그 | 예외 경로. SQL 대체 아님 |

권장 한 줄:

```
png/jpeg → 역할 판별
  (a) 보고서 내부 → VLM 캡션 + OCR 숫자 → 부모 문서 청크에 부착
  (b) 페이지 스캔 → Docling 이미지 파이프라인 (RapidOCR korean)
                  → 01-pdf 스캔 분기와 동일. VLM은 OCR 실패 시
```

## 권장 파이프라인

```
업로드 png/jpeg (또는 문서에서 추출된 이미지)
  1. 시그니처
       PNG / JPEG. 확장자만 믿지 말 것
       TIFF면 18로, PDF 렌더면 01로
       BMP/WEBP도 Docling 이미지 입력. 이 분기와 같음
  2. 역할 판별
       부모 문서 있음 + 작은 그림     → (a) 삽입 그림
       A4 비율, 고해상, 단독 파일     → (b) 스캔 페이지
       엑셀 격자·리본이 보임          → 스크린샷 표
  3a. 삽입 그림
       VLM 한 줄 캡션 (차트 종류, 축, 기간)
       OCR로 숫자·품번 추출 (RapidOCR korean)
       parent_doc_id, section, caption 연결
  3b. 스캔 페이지
       Docling 이미지 파이프라인 / PDF OCR
       RapidOCR korean (문서 엔진)
       선택: ColPali/ColQwen 페이지 인덱스
       텍스트 층이 생기면 01-pdf 스캔과 동일 청크
       OCR이 비면 VLM 보조
  3c. 엑셀 스크린샷
       표 OCR. confidence 낮음 플래그
       가능하면 원본 xlsx를 찾아 04로
  4. 메타
       제품/차종, 부모 문서, 페이지, 이미지 역할
       parser=docling_image, ocr_engine=rapidocr, ocr_lang=korean
  5. MCP
       get_page_image, get_caption
       숫자는 캡션/OCR 근거와 함께
```

원본 이미지는 객체 저장한다. 캡션만 남기고 그림을 버리지 않는다.

## 단계별 권장

### 1. 두 갈래를 먼저 나눈다

**(a) 보고서 내부 차트·사진**  
월보 Pareto, 공정 사진, 불량 확대, 그래프. 부모 PDF/DOCX/PPTX가 있다. 이미지는 독립 문서가 아니라 **부모 섹션의 자식**이다.

**(b) 촬영·스캔 전체 페이지**  
클레임 용지를 찍은 JPEG, 도장 있는 성적서. 사실상 스캔 PDF 한 장이다. 가족 B로 승격한다.

판별 힌트: 부모 첨부 여부, 픽셀 크기, A4 종횡비, 여백, 본문 텍스트 밀도. 애매하면 (b)로 두고 캡션만으로 끝내지 않는다.

### 2. (a) VLM 캡션 + OCR 숫자

품질 차트는 본문 XML에 숫자가 없다. 부모 문서 파서가 그림을 건너뛰면 월보 핵심이 사라진다. OCR이 거의 없는 차트·도표는 VLM이 본체다.

- VLM: 차트 유형, 축, 기간, 상위 항목을 한 줄로
- OCR: 막대/표 안의 숫자, 품번, 한글 라벨. RapidOCR `korean`
- 청크 앞에 부모 breadcrumb를 붙인다  
  `[문서] 2024-03 월보 [섹션] 3. 클레임 현황 [그림] Pareto`
- 벡터에는 캡션+OCR 텍스트. 원본은 별도 저장
- 답변 시 `get_page_image`로 그림을 보여 준다. 숫자만 믿게 하지 않는다

### 3. (b) 스캔 페이지 — Docling OCR이 기본

01-pdf의 스캔 분기와 같다. 커스텀 VLM만으로 스캔을 처리하지 않는다.

- Docling 이미지 파이프라인(또는 가상 PDF 후 StandardPdfPipeline OCR)
- RapidOCR `korean`. 범용 영어 OCR만 쓰지 않는다. PP-OCR v4/v5에 korean이 있다. v6는 korean 별칭만 있고 실제 미지원이니 v4/v5를 고정한다
- 레이아웃(제목/표/도장)이 중요하면 페이지 비전(ColPali)을 보조 인덱스로
- JPEG 한 장은 한 페이지 청크다. 2장 이상이면 페이지 단위로 나눈다
- 여러 장을 한 폴더로 올리면 가상 PDF로 묶어 01 스캔 경로를 태운다
- OCR 텍스트가 비면 그때 VLM을 보조로 켠다

### 4. 엑셀 화면 JPEG

담당자가 시트 일부를 캡처해 메일에 붙이는 경우가 많다.

- 표 OCR을 시도한다
- `ocr_table=true`, `confidence=low`를 메타에 남긴다
- 이 숫자는 SQL 팩트가 아니다. 답변에 “스크린샷 OCR, 원본 시트 확인 필요”를 붙인다
- 같은 메일에 xlsx 첨부가 있으면 04 경로가 우선이다

### 5. EXIF

촬영 시각·GPS는 사내 스캔에서 거의 비어 있거나 복사기다. 문서 일자로 쓰지 않는다. 부모 문서 날짜·파일명이 진실이다.

### 6. MCP

1. `get_page_image(doc_id, page)` — 차트/스캔 확인
2. `get_caption(image_id)` — VLM+OCR 텍스트
3. 부모 `get_section`과 함께 반환

검색만으로 차트 숫자를 단정하지 않는다.

## 흔한 실패

- CLIP 유사 사진 검색으로 다른 차종 공정 사진이 올라옴
- 차트 이미지를 건너뛰어 월보 본문만 인덱싱
- 스캔 JPEG를 VLM 한 줄만 하고 OCR을 생략
- PNG를 docx인 양 SimplePipeline에 넣음
- RapidOCR v6 `ko` 별칭으로 한글이 빈 문서가 됨
- 엑셀 캡처를 고신뢰 표로 적재
- 저해상 사진 OCR을 교정 없이 품번에 사용
- 삽입 그림(a)을 독립 문서로 임베딩해 부모 8D와 끊김

## 하지 말 것

- 품질 문서를 일반 사진 CLIP 인덱스로 넣기
- PNG를 docx인 양 Docling SimplePipeline에 넣기
- 전체 페이지 스캔을 커스텀 VLM만으로 처리하기
- EXIF 날짜를 클레임 일자로 쓰기
- 스크린샷 OCR 표를 MariaDB 2층에 넣기
- 원본 이미지를 버리고 캡션만 남기기

## 인접 포맷

- 멀티페이지 스캔 → [18-tiff.md](18-tiff.md)
- 스캔 PDF → [01-pdf.md](01-pdf.md) 스캔 분기
- BMP/WEBP → Docling 이미지 입력. 이 문서와 같은 분기
- 메일 cid/첨부 이미지 → [11-msg.md](11-msg.md), [12-eml.md](12-eml.md)
- PPTX 차트 → [07-pptx.md](07-pptx.md). 슬라이드에서 추출 후 이 문서 (a)
