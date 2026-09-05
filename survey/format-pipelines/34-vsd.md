# Visio VSD 권장 파이프라인

- 배경: 시장품질 레거시 공정흐름도·품질계통도가 Visio 2003–2010(`.vsd`, OLE)로 남아 있다. python은 이 포맷을 잘 못 읽는다. Docling은 Visio를 파싱하지 않는다.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

`.vsd`는 `.vsdx`가 아니다. OLE 바이너리라서 **직접 파싱하지 않는다.** LibreOffice(libvisio) 또는 Visio로 `.vsdx`(우선) 또는 PDF로 바꾼 뒤 [33-vsdx.md](33-vsdx.md) 또는 [01-pdf.md](01-pdf.md)를 탄다. 원본은 삭제하지 않는다.

| 선택 | 판단 |
|---|---|
| python으로 `.vsd` 직접 읽기 | 하지 말 것. 충실도 낮음 |
| python `vsdx`에 OLE 투입 | 하지 말 것. vsdx 전용 |
| OLE 텍스트 dump / strings | 하지 말 것. 도형 관계 붕괴 |
| LibreOffice(libvisio)/Visio → vsdx 후 33 | **기본 경로** |
| 변환 실패 시 PDF → 01 | **보조 경로** |
| libvisio `vsd2text`만 | 차선. 라벨만, 커넥터 유실 |
| 변환본만 남기고 원본 삭제 | 하지 말 것 |
| vsd를 19 XML로 취급 | 하지 말 것 |
| Docling에 vsd 투입 | 하지 말 것. 미지원 |

권장 한 줄:

```
.vsd (원본 보관)
  → 시그니처(OLE, vsdx/msg 아님)
  → LibreOffice(libvisio) 또는 Visio → .vsdx (우선) | PDF (보조)
  → 33-vsdx 또는 01-pdf
```

## 권장 파이프라인

```
업로드 .vsd
  1. 시그니처
       OLE Compound    → 진짜 .vsd
       ZIP/OOXML       → 확장자만 잘못된 vsdx. 이름만 고치고 33
       PDF             → 01-pdf
       Outlook/엑셀 OLE → 11 / 05. 여기 아님
  2. 변환
       soffice --headless --convert-to vsdx   # 엔진은 libvisio
       실패 시 --convert-to pdf
       Windows Visio COM이 있으면 품질 우선
  3. 변환 검증
       페이지 수, 한글 깨짐, 커넥터 잔존
  4. 이후
       vsdx → 33 (vsdx 셰이프 텍스트 + 페이지 PNG + VLM)
       pdf  → 01 (스캔/도면 페이지)
  5. 메타
       converted_from=vsd, converter=libreoffice|visio
  원본 .vsd 보관
```

## 단계별 권장

### 1. 확장자가 아니라 시그니처

공유 폴더에는 `.vsd`인데 실제로는 `.vsdx`인 파일이 있다. OLE `.msg`/`.xls`와 매직이 같다.

```bash
file process_flow.vsd
# Visio 2003–2010 / Composite Document  → 변환
# Microsoft Visio 2013+ / Zip archive   → 33으로 바로
# PDF document                          → 01
```

잘못된 파일을 LibreOffice에 넣으면 실패 원인 추적이 어렵다. python `vsdx` 라이브러리에 OLE를 넣지 않는다. `vsdx`는 `.vsdx` 전용이다.

### 2. 변환은 LibreOffice(libvisio) 또는 Visio

LibreOffice의 vsd 임포트 엔진은 **libvisio**(Document Liberation Project)다. 직접 `vsd2text` / `vsd2xhtml`는 라벨만 나오고 연결선·레이어가 빠진다. 기본은 soffice → vsdx다.

```bash
soffice --headless --norestore --nolockcheck \
  --convert-to vsdx \
  --outdir /data/normalized \
  process_flow.vsd
```

vsdx가 실패하면 PDF다. 텍스트 추출 모드는 쓰지 않는다.

- 한글 폰트(`fonts-noto-cjk` / `fonts-nanum`)를 컨테이너에 넣는다. 없으면 박스 글자가 `□□`
- soffice는 동시 실행에 약하다. 워커 하나, 또는 파일마다 별도 `UserInstallation`
- 타임아웃을 건다. 깨진 OLE가 soffice를 붙잡는다
- 실패는 `failed_vsd`로 남기고 배치를 멈추지 않는다
- Windows Visio가 있으면 COM 내보내기가 커넥터·레이어에서 낫다. Linux MCP면 LibreOffice가 기본이다

python visio 파서, olefile로 스트림을 긁는 경로는 입고 기본이 아니다. 셰이프 좌표만 나오고 한글·연결선이 빠진다.

### 3. 변환 후 검증

표본이 많지 않아도 게이트는 아래면 고정된다.

1. 변환 성공률
2. 페이지 수: 원본 vs 변환본
3. 한글 깨짐 (`□`, `?`, 모지바케)
4. 박스 라벨 수 (공정명·품번)
5. 커넥터 유실 — 흐름도면 실패에 가깝다

페이지가 줄거나 화살표가 사라지면 해당 파일만 Visio COM 또는 PDF 비전으로 보낸다. 빈 페이지를 33에 넣지 않는다.

### 4. 이후는 가족 H

변환된 vsdx는 파생물이다. 청크 규칙은 33과 같다.

- `vsdx` 셰이프 텍스트 + 페이지 PNG + VLM
- MCP: `list_pages`, `get_page_image`, `get_shape_text`
- XML 원문 청크 금지

PDF로 간 경우는 도면 페이지다. 디지털 본문이 거의 없으면 01의 스캔/이미지 분기다. 표형 원장으로 착각하지 않는다.

## 흔한 실패

- python `vsdx`로 vsd를 열어 빈 텍스트를 인덱싱
- OLE `.vsd`를 ZIP 파서에 넣음
- `vsd2text`만 돌려 계통도가 박스 나열이 됨
- 한글 폰트 없이 변환해 공정명이 `????`
- 페이지 수는 맞는데 커넥터가 사라짐
- 원본을 지워 재변환이 안 됨
- 변환 PDF를 표로 보고 SQL에 넣음
- Docling이 Visio를 받는다고 입고 로그에 원본만 남기기

## 하지 말 것

- `.vsd`를 strings/마크다운으로 dump 해서 청크
- 웹 변환 API에 사내 공정도 업로드
- 변환 실패 파일을 빈 페이지로 인덱싱
- Docling이 “Visio를 받는다”고 입고 로그에 원본만 남기기
- 원본 삭제
- 가족 C(`query_tables`)로 우회

`.vsd`는 포맷 문제가 아니라 **정규화 한 단계**다. 게이트만 두면 이후는 33 또는 01과 같다.

## 인접 포맷

- `.vsdx` → [33-vsdx.md](33-vsdx.md). 이 문서의 도착점
- 배포 PDF 도면 → [01-pdf.md](01-pdf.md)
- `.ppt` → [08-ppt.md](08-ppt.md). 같은 LibreOffice 게이트, 도착은 가족 D
- `.doc`/`.xls` → [03-doc.md](03-doc.md) / [05-xls.md](05-xls.md). 같은 OLE, 다른 가족
- Outlook `.msg` → [11-msg.md](11-msg.md). Visio가 아님
