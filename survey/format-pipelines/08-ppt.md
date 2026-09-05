# .ppt 권장 파이프라인

- 배경: 시장품질 레거시 발표자료(`.ppt`, 97–2003)를 RAG/MCP에 넣을 때 정규화 게이트를 둔다.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

`.ppt`는 `.pptx`와 같은 슬라이드가 아니다. OLE 컴파운드 바이너리라서 **python-pptx가 읽지 못한다.** Docling은 PPT를 받더라도 내부는 LibreOffice 변환이다. 입고에서 soffice를 숨기지 않는다. **명시적 LibreOffice → `.pptx` 후 [07-pptx.md](07-pptx.md)** 가 기본이다. 원본은 삭제하지 않는다.

권장 한 줄:

```
.ppt (원본 보관)
  → 시그니처 확인 (확장자만 믿지 말 것)
  → LibreOffice headless + UserInstallation + timeout + 한글 폰트 → .pptx
  → 07-pptx 파이프라인 (슬라이드 1장 = 청크 1개)
```

| 선택 | 판단 |
|---|---|
| python-pptx로 `.ppt` 직접 읽기 | 하지 말 것. 포맷이 다름 |
| antiword/catppt 텍스트 dump | 하지 말 것. 표·한글·노트 붕괴 |
| Docling에 `.ppt`만 넣고 soffice를 숨김 | 하지 말 것. 실패 원인 추적이 안 됨 |
| LibreOffice → `.pptx` 후 07 | **기본 경로** |
| 변환본만 남기고 원본 삭제 | 하지 말 것 |
| PDF로 먼저 보내기 | 기본 아님. 시각 검색이 필요할 때만 |

Docling 지원 목록에 PPT가 있어도 “LibreOffice 설치 시”다. 변환 게이트를 입고에 남긴다.

## 권장 파이프라인

```
업로드 .ppt
  1. 시그니처
       OLE Compound    → 진짜 .ppt
       ZIP/OOXML       → 확장자만 잘못된 .pptx. 이름만 고치고 07
       PDF             → 01-pdf
  2. LibreOffice 정규화
       soffice --headless --convert-to pptx
       -env:UserInstallation=file:///…  (파일마다 별도 프로필)
       timeout 필수 (issue #3819)
       한글 폰트 필수
  3. 변환 검증
       슬라이드 수, 한글 깨짐, 노트 유무
  4. 이후는 07-pptx 와 동일
       슬라이드 청크 + 노트
       bar/pie/line → Docling chart extraction
       사진·공정 이미지 → VLM
  5. 메타
       converted_from=ppt, converter=libreoffice
  원본 .ppt 보관
```

## 단계별 권장

### 1. 확장자가 아니라 시그니처

시장품질 공유 폴더에는 `.ppt`인데 실제로는 `.pptx`인 파일이 많다.

```bash
file monthly_review.ppt
# PowerPoint 97-2003          → LibreOffice 변환
# Microsoft PowerPoint 2007+  → 확장자만 잘못된 pptx
# PDF document                → 01-pdf 로 재분류
```

잘못된 파일을 LibreOffice에 넣으면 실패 원인 추적이 어려워진다.

### 2. 변환은 LibreOffice, 파싱은 07

```bash
soffice --headless --norestore --nolockcheck \
  -env:UserInstallation=file:///tmp/lo-profile-$JOB \
  --convert-to pptx:"Impress MS PowerPoint 2007 XML" \
  --outdir /data/normalized \
  monthly_review.ppt
```

운영에서 지킬 것:

- **한글 폰트**를 컨테이너에 넣는다. `fonts-noto-cjk` / `fonts-nanum`이 없으면 변환은 성공해도 본문이 `□□`가 된다.
- LibreOffice는 프로세스 동시 실행에 약하다. 워커 하나, 또는 파일마다 별도 `UserInstallation`.
- **타임아웃**을 건다. 깨진 `.ppt`가 soffice를 붙잡는다. Docling이 soffice를 부를 때도 timeout이 없다(issue #3819). 기본 프로필 잠금으로 병렬 변환이 조용히 실패한다.
- 변환 실패는 배치를 멈추지 않고 `failed_ppt`로 남긴다.
- 암호·매크로·OLE 임베디드 엑셀/차트는 자주 손실된다.

Windows에 PowerPoint가 있으면 COM 품질이 더 높다. MCP 서버가 Linux면 LibreOffice가 맞다.

Docling에 `.ppt`를 직접 넣어도 같은 soffice를 탄다. 입고 로그에는 `converter=libreoffice`와 변환본 경로를 남긴다. soffice 부재와 깨진 파일을 가릴 수 있어야 한다.

### 3. 변환 후 검증

표본이 많지 않아도 아래만 보면 게이트를 고정할 수 있다.

1. 변환 성공률
2. 슬라이드 수: 원본 vs 변환본
3. 한글 깨짐 (`□`, `?`, 모지바케)
4. 발표자 노트 잔존
5. 표·차트 이미지 유실

슬라이드가 줄거나 노트가 비면 해당 파일만 Windows PowerPoint 경로로 보낸다.

### 4. 이후는 가족 D

변환된 `.pptx`는 파생 산출물이다. 청크 규칙은 07과 같다.

- 슬라이드 1장 = 청크 1개
- bar/pie/line은 Docling chart understanding, 사진·공정 이미지는 VLM
- MCP는 `list_slides`, `get_slide(n)`

PDF로 가는 경우는 07과 같다. 레이아웃·스탬프·비전 검색이 필요할 때만.

## 흔한 실패

- python-pptx에 `.ppt`를 넣어 즉시 실패하거나 빈 문서로 인덱싱한다.
- Docling이 PPT를 받는다고 원본만 넣고, soffice 타임아웃·프로필 충돌을 놓친다.
- 한글 폰트 없이 변환해 품번·고장모드가 `□□`가 된다.
- 슬라이드 수는 맞는데 노트가 사라져 원인 서술이 없다.
- 확장자 위조 `.pptx`를 OLE 변환기에 넣어 로그가 섞인다.
- 원본을 지워 재변환이 불가능하다.

## 하지 말 것

- `.ppt`를 마크다운/텍스트로 바로 dump 해서 청크
- 웹 변환 API에 사내 품질 문서 업로드
- 변환 실패 파일을 빈 슬라이드로 인덱싱
- Docling이 “PPT를 받는다”고 입고 로그에 원본만 남기기
- soffice를 기본 프로필로 병렬 실행하기 (issue #3819)
- 원본 삭제

`.ppt`는 포맷 문제가 아니라 **정규화 한 단계**다. 게이트만 두면 이후는 07과 같다.

## 인접 포맷

- `.pptx` → [07-pptx.md](07-pptx.md). 이 문서의 도착점.
- `.pptm` → [28-pptm.md](28-pptm.md). OOXML이면 매크로 제거 후 07. OLE면 여기.
- `.odp` → [26-odp.md](26-odp.md). ODF는 Docling ODP가 우선. 변환은 폴백.
- `.doc` → [03-doc.md](03-doc.md). 같은 LibreOffice 게이트, 도착은 가족 A.
- `.xls` → [05-xls.md](05-xls.md). 같은 게이트, 도착은 가족 C (RAG 금지).
