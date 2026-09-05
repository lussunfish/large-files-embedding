# TIFF 권장 파이프라인

- 배경: 시장품질 RAG/MCP에서 TIFF(특히 멀티페이지 G4 팩스/스캔)를 어떻게 넣을 것인가. 가족 F/B
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

TIFF는 사진 포맷이 아니라 **스캔 문서 컨테이너**인 경우가 많다. 페이지로 쪼개 스캔 PDF와 같이 처리한다. 100페이지 TIFF를 한 청크로 넣지 않는다.

Docling은 2026-09 기준 TIFF를 이미지 파이프라인 입력으로 받는다. 멀티페이지는 **직접 분리하거나 Docling이 프레임을 페이지로 나누게** 한다. OCR은 RapidOCR `korean`. SimplePipeline(docx인 양)은 쓰지 않는다.

| 선택 | 판단 |
|---|---|
| 멀티페이지 TIFF를 한 덩어리로 임베딩 | 하지 말 것 |
| Docling 이미지 파이프라인 (분리 또는 Docling 페이지화) + RapidOCR korean | **기본 경로** |
| PDF로 감싼 뒤 01-pdf 스캔 분기 | 가능. 운영이 단순하면 권장 |
| CLIP 사진 임베딩 | 하지 말 것 |
| TIFF를 docx/SimplePipeline에 넣기 | 하지 말 것 |
| 페이지를 메모리에 전부 로드 | 하지 말 것. 스트리밍 |
| 영어 OCR만 | 하지 말 것. 한글 클레임 서류 |

권장 한 줄:

```
.tiff (멀티페이지 G4) → 페이지 스트리밍 분리 또는 Docling 페이지화
  → 페이지 = 스캔 PDF 1장
  → Docling 이미지/PDF OCR (RapidOCR korean, 선택 ColPali)
  → 또는 PDF wrap 후 01-pdf 스캔 분기
```

## 권장 파이프라인

```
업로드 .tiff / .tif
  1. 시그니처
       TIFF little/big endian. 확장자만 믿지 말 것
       단일 프레임 사진이면 17 (a)로 보낼 수 있으나
       클레임 스캔이면 이 경로 유지
  2. 페이지 수·압축
       G4(CCITT) 팩스, LZW, JPEG 타일
       페이지 수, 해상도(200/300dpi), 용량
  3. 페이지 처리
       a. 스트리밍 분리: 한 장씩 디코드 후 PNG/JPEG 방출
       b. Docling 이미지 백엔드: 프레임 = 페이지로 페이지화
       100장을 한 번에 RAM에 올리지 않음
  4. OCR
       Docling 이미지/PDF OCR, RapidOCR korean
       표·도장·수기는 VLM/ColPali 보조
  5. (운영 대안) PDF wrap
       페이지 순서 유지한 스캔 PDF
       → 01-pdf 스캔 분기 (OCR / 비전)
  6. 메타
       클레임번호, 팩스 수신일, 페이지, parent tiff
       parser=docling_image, ocr_engine=rapidocr, ocr_lang=korean
  7. MCP
       get_page_image(doc, page)
       검색은 페이지 필터
```

원본 TIFF는 보관한다. 파생 PDF/OCR JSON을 재처리용으로 남긴다.

## 단계별 권장

### 1. 왜 스캔 PDF와 같은가

시장품질 TIFF는 대부분 멀티페이지 G4 팩스·복합기 스캔이다. 클레임 신청서, 거래명세서, 수기 8D, 도장 성적서.

가족 F(이미지)로 시작하지만 **내용이 문서면 가족 B로 승격**한다. 17번의 (b)와 같고, 페이지만 많다.

단일 프레임 사진 TIFF는 드물다. 그 경우에만 17 (a)로 보낸다.

### 2. 페이지 분리, 통짜 금지

100페이지 TIFF를 한 청크로 넣으면 검색이 한 파일에 붕괴한다.

- 페이지 1장 = 스캔 PDF 1장 = 기본 검색 단위
- Docling 이미지 백엔드는 멀티프레임 TIFF를 페이지로 나눈다. 그걸 쓰거나, 입고에서 직접 분리한다
- 어느 쪽이든 **청크는 페이지 단위**다. Docling이 페이지화했다고 파일 전체를 한 벡터로 넣지 않는다
- 표가 여러 장에 걸치면 페이지 범위를 메타로 묶는다
- 빈 장·표지·뒷면 공백은 OCR 후 텍스트 길이로 스킵한다

### 3. 한글 OCR

팩스 G4는 200dpi, 기울기, 스탬프, 수기가 겹친다.

- Docling OCR + RapidOCR `korean`. 영어 엔진만 쓰면 품번·성명이 깨진다
- PP-OCR v4/v5에 korean이 있다. v6는 korean 별칭만 있고 실제 미지원이니 v4/v5를 고정한다
- 전처리: 기울기 보정, 대비. 원본은 유지
- 신뢰도 낮은 페이지는 `ocr_confidence=low`. 답변에 페이지 이미지를 붙인다
- 수기 비율이 높으면 OCR만 믿지 말고 ColPali/VLM을 보조로 둔다

### 4. PDF wrap

운영이 이미 01-pdf 스캔 분기를 갖고 있으면 TIFF를 그 입구로 보내는 편이 단순하다.

```
tiff → (페이지 순서 유지) 스캔 PDF → 01-pdf 스캔 분기
```

변환은 입고 게이트일 뿐이다. 원본 TIFF를 지우지 않는다. `converted_from=tiff`, `page_count`를 메타에 남긴다.

LibreOffice는 TIFF 기본 경로가 아니다. Docling SimplePipeline도 아니다.

### 5. 대용량 스트리밍

멀티페이지 TIFF는 압축 전 픽셀이 수 GB가 될 수 있다.

- 페이지 단위로 연다. 전체 디코드 금지
- Docling에 통째로 넣더라도 워커는 페이지 스트림으로 취급한다
- 워커 타임아웃은 페이지 수에 비례
- 실패 페이지는 건너뛰고 `failed_page`를 남긴다. 문서 전체를 버리지 않는다
- 100MB급 첨부로 메일에 오면 11/12가 파일을 저장한 뒤 이 파이프라인이 연다

### 6. MCP

1. `list_documents` — 클레임번호·기간 필터
2. `get_page_image(doc_id, page)` — 스캔 원문
3. `search_passages` — 페이지 단위 하이브리드
4. 표 숫자가 필요하면 OCR 표 객체. 원본 확인을 강제

Codex는 텍스트 hit만으로 클레임 서류를 단정하지 않고 해당 페이지를 연다.

## 흔한 실패

- 100페이지 TIFF 1청크 → 다른 클레임이 한 검색 결과에 섞임
- 영어 OCR로 한글 신청서가 빈 문서가 됨
- RapidOCR v6 `ko` 별칭으로 한글이 빠짐
- G4 멀티페이지를 첫 장만 읽고 입고 완료
- 전체 프레임을 RAM에 올려 워커 OOM
- CLIP으로 “비슷한 스캔 용지”를 다른 건 서류와 매칭
- TIFF를 docx/SimplePipeline에 넣어 빈 JSON

## 하지 말 것

- 멀티페이지 TIFF를 한 벡터로 넣기
- 첫 페이지만 OCR하고 나머지를 버리기
- 17번 삽입 그림(VLM 한 줄)만 하고 끝내기
- TIFF를 docx/Docling SimplePipeline에 넣기
- 변환 PDF만 남기고 원본 스캔을 삭제하기

## 인접 포맷

- 스캔 PDF → [01-pdf.md](01-pdf.md). wrap 후 같은 분기
- 단일 PNG/JPEG 스캔 → [17-png-jpeg.md](17-png-jpeg.md) (b)
- 메일 첨부 TIFF → [11-msg.md](11-msg.md), [12-eml.md](12-eml.md) 후 재입고
- 디지털 PDF(텍스트 층) → 01-pdf 디지털 분기. TIFF와 섞지 말 것
