# 리뷰: 메일·이미지·컨테이너 파이프라인 (2026-09)

대상: `11-msg.md`, `12-eml.md`, `17-png-jpeg.md`, `18-tiff.md`, `29-mht.md`, `30-zip.md`.  
근거: Docling supported formats (2026-09-04), `EmailBackendOptions`, RapidOCR 언어표.  
패치: 위 여섯 문서를 제자리에서 고쳤다. 체재는 하다/다.

## 한 줄

메일 본문은 Docling이 읽는다. 첨부 바이너리는 여전히 직접 푼다. 스캔 이미지는 Docling OCR이 기본이다. MHT·ZIP은 Docling 입력이 아니다.

## 11-msg.md — 본문 금지 문구를 뒤집음

**이전.** `Docling에 MSG 직접 투입 | 하지 말 것`. OLE라서 extract-msg/Tika만 기본.

**사실 (2026-09).** Docling이 `.eml`/`.msg`를 네이티브로 파싱한다. extra는 `mail-parser`(slim은 `format-email` + `python-oxmsg`). `EmailBackendOptions.list_attachments`는 파일명·content-type만 문서에 붙인다. **첨부 바이트는 절대 임베드하지 않는다.**

**패치.**

- 본문·헤더: Docling email 백엔드 = extract-msg/Tika와 **동등 기본**. 가족 A형 RAG(메일 1통 = 문서 1개).
- 첨부: 이름 목록 ≠ fan-out. 원본 바이트 저장 후 xlsx→04, pdf→01, png→17, 중첩 msg/eml→재귀.
- extract-msg는 유지. RTF 본문, named properties, Conversation-Index는 OLE 쪽에서 더 잘 남는다.
- “하지 말 것”에서 Docling 본문 금지를 빼고, `list_attachments` 대체 사용을 넣었다.

**남는 위험.** Docling이 본문을 읽었다고 첨부 파이프라인을 끄는 운영. 품질 메일은 첨부가 본체인 경우가 많다.

## 12-eml.md — 같은 하이브리드

**이전.** `email.parser`만 기본. Docling 금지는 명시하지 않았으나 HTML→PDF→Docling만 금지.

**사실.** MIME `.eml`도 같은 email 백엔드. 첨부 바이너리는 역시 안 온다.

**패치.**

- Docling / `email.parser` 동등 기본. charset·cid·중첩 파트를 직접 통제할 때는 parser.
- `list_attachments`만으로 첨부 처리 금지. 중첩 `.eml`/`.msg`는 깊이 제한 재귀.
- HTML을 브라우저 렌더 후 PDF로 Docling 보내는 금지는 유지.

**EML≠MHT.** 스레드 헤더가 있는 메일은 12, 웹 보관 MIME은 29.

## 17-png-jpeg.md — 스캔 기본을 Docling OCR로

**이전.** 스캔(b)도 “OCR + 선택 ColPali”이나 엔진이 추상적. “Docling을 docx처럼 적용 금지”가 이미지 파이프라인 전체 금지처럼 읽힘. 차트(a)와 스캔(b)의 VLM 비중이 비슷해 보임.

**사실.** Docling 입력: PNG, JPEG, TIFF, BMP, WEBP. 이미지 파이프라인/OCR. RapidOCR PP-OCR v4/v5에 `korean`. v6는 `ko` 별칭만 있고 korean 미지원.

**패치.**

- (b) 전체 페이지 스캔: **Docling 이미지/PDF OCR이 기본**. 커스텀 VLM-only는 기본이 아님.
- (a) 차트·삽입 그림: OCR 텍스트가 없으면 **VLM 유지**. RapidOCR korean으로 숫자·품번도 뽑는다.
- SimplePipeline(docx인 양) 금지는 유지. CLIP 금지도 유지.
- BMP/WEBP는 같은 분기로 인접 포맷에 적음.

## 18-tiff.md — Docling TIFF + 페이지 단위

**이전.** 페이지 분리 후 스캔 PDF와 동일. “TIFF를 Docling SimplePipeline에 넣기” 금지. Docling이 TIFF를 받는다는 말이 없음.

**사실.** Docling 이미지 백엔드가 멀티프레임 TIFF를 페이지로 나눈다.

**패치.**

- 기본: Docling 이미지 파이프라인 + RapidOCR korean. 직접 스트리밍 분리 **또는** Docling 페이지화.
- 어느 쪽이든 청크는 페이지 단위. 100페이지 1벡터 금지는 유지.
- PDF wrap → 01-pdf는 운영 대안으로 유지.
- SimplePipeline 금지는 유지. 한글 OCR 유지는 v4/v5 고정까지 명시.

## 29-mht.md — 경로 유지, Docling 미지원만 명시

**이전.** MIME에서 HTML 추출 → 13, cid → 17. 맞다.

**사실.** Docling 지원 목록에 MHT/MHTML이 없다. (Rust 포트 docling.rs는 MHTML을 확장으로 두지만 Python Docling 기준이 아니다.)

**패치.**

- MIME → 13 경로 유지.
- 표에 “Docling에 MHT 직접 투입 하지 말 것”을 추가.
- email 백엔드로 보내 메일 헤더로 오인하지 말 것.

## 30-zip.md — 경로 유지, .dclx만 예외

**이전.** zip slip, 압축 폭탄, `__MACOSX` 스킵, 암호는 실패 큐, 중첩 깊이 제한, 엔트리마다 포맷 라우터. 맞다.

**사실.** Docling은 일반 ZIP을 문서 컨테이너로 받지 않는다. 예외는 DocLang archive `.dclx`.

**패치.**

- slip/폭탄/재귀 문장은 그대로.
- “일반 ZIP을 Docling에 넣지 말 것. `.dclx`만 예외”를 결론·표·하지 말 것에 넣음.
- OOXML/ODF/HWPX 위장 ZIP 재분류는 기존과 같음.

## 표

| 파일 | 판정 | 핵심 변경 |
|---|---|---|
| 11-msg.md | **고침** | 본문 Docling 허용. 첨부 fan-out은 필수. extract-msg는 OLE 보조 |
| 12-eml.md | **고침** | 본문 Docling/`email.parser`. 첨부·중첩 메일 재귀 |
| 17-png-jpeg.md | **고침** | 스캔 = Docling OCR 기본. VLM은 차트/OCR 실패 |
| 18-tiff.md | **고침** | Docling TIFF. 분리 또는 페이지화. RapidOCR korean |
| 29-mht.md | **유지+주석** | MIME→13 유지. Docling 미지원 명시 |
| 30-zip.md | **유지+주석** | slip/폭탄/재귀 유지. ZIP≠Docling (`.dclx` 제외) |

## README와 맞물림

`README.md` 한 줄은 아직 대략 맞다.

- 11/12: “본문 RAG + 첨부 재분기” — 본문 파서에 Docling이 추가된 것뿐.
- 17: “OCR + VLM. 스캔이면 PDF 스캔 경로” — 스캔 OCR을 Docling으로 고정한 것이 차이.
- 29/30: 그대로.

README 표까지 손보지는 않았다. 이 리뷰 범위 밖이다.

## 운영 체크

1. Docling email extra(`mail-parser`)가 입고 이미지에 있는지.
2. 메일 워커가 본문 convert와 첨부 바이트 추출을 **같은 잡에서** 하는지. `list_attachments=true`만 켜고 끝내지 말 것.
3. RapidOCR을 v4 또는 v5 + `korean`으로 고정. v6 `ko` 별칭 금지.
4. `.mht`를 `.eml` 게이트에 넣지 말 것. `.dclx`를 월간 팩 ZIP 게이트에 넣지 말 것.
5. 중첩 메일/ZIP 깊이 카운트를 공유할 것.
