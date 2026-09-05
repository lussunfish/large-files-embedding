# .doc 확장자 처리 방법

- 배경: 시장품질 문서 파이프라인에서 레거시 Word(`.doc`)를 어떻게 넣을 것인가
- 관련 문서: `market-quality-rag-improvement.md`, `docx-pipeline.md`, `format-pipelines/03-doc.md`
- 재검토: 2026-09-05

## 결론

`.doc`는 `.docx`와 같은 Word가 아니다. 97–2003 바이너리(OLE)라서 python-docx는 직접 못 읽는다. Docling은 LibreOffice가 있으면 내부에서 변환해 받지만, **입고에서 soffice를 명시하는 것**이 디버깅·timeout에 안전하다 (2026-07 issue #3819: hang, 기본 프로필 충돌).

| 선택 | 판단 |
|---|---|
| python-docx로 `.doc` 직접 읽기 | 하지 말 것 |
| `antiword` / `catdoc`으로 텍스트만 뽑기 | 하지 말 것 (표·한글 깨짐) |
| LibreOffice로 `.docx` 변환 후 Docling | **기본 경로**. timeout + UserInstallation |
| Docling에 `.doc`만 넘기고 soffice를 숨기기 | 비추천. 실패 원인 구분 불가 |
| 변환본만 남기고 원본 삭제 | 하지 말 것. 원본은 보관 |
| 엑셀처럼 SQL로 빼기 | 해당 없음. `.doc`는 서술 문서 |

```
.doc (원본 보관)
  → 실제 포맷 판별 (확장자만 믿지 말 것)
  → LibreOffice headless → .docx
  → Docling JSON (기존 docx와 동일)
  → 계층 청크 / 벡터
```

텍스트 추출기(`antiword`, Apache Tika 텍스트 모드)는 시장품질 8D·대책 보고서의 표와 제목 계층을 거의 버린다.

## 왜 변환이 필요한가

- `.docx` = ZIP + XML. Docling이 제목/표/리스트를 그대로 읽음
- `.doc` = OLE 컴파운드 바이너리. 표, 한글, 임베디드 엑셀이 텍스트 추출에서 쉽게 붕괴
- 확장자가 `.doc`인데 실제로는 `.docx`이거나 RTF인 파일도 흔함

그래서 첫 단계는 변환이 아니라 **파일 시그니처 확인**이다.

```bash
file claim_8d.doc
# Word 97-2003 Document          → LibreOffice 변환
# Microsoft Word 2007+           → 확장자만 잘못된 docx. 이름만 고치기
# Rich Text Format               → .rtf로 취급
```

잘못된 확장자를 LibreOffice에 넣으면 실패 원인 추적이 어려워진다.

## 변환은 LibreOffice, 파싱은 Docling

```bash
soffice --headless --norestore --nolockcheck \
  --convert-to docx:"MS Word 2007 XML" \
  --outdir /data/normalized \
  claim_8d.doc
```

운영에서 지킬 것:

- **한글 폰트**를 컨테이너에 넣기. 없으면 변환은 성공해도 본문이 `□□`가 된다. `fonts-noto-cjk` / `fonts-nanum` 필수.
- LibreOffice는 **프로세스 동시 실행에 약함**. 워커 하나, 또는 파일마다 별도 `UserInstallation`. Docling 내부 soffice도 같다 (#3819). 대량은 JODConverter 풀.
- **timeout을 반드시 건다.** 깨진 `.doc`와 모달 대화상자가 headless에서 무한 대기를 만든다.
- 변환 실패는 전체 배치를 멈추지 말고 `failed_doc`으로 남기기.
- 암호/매크로/OLE 임베디드 엑셀은 자주 손실된다. 임베디드 표가 본문이면 변환 후 표 개수를 원본과 비교하는 검증이 필요하다.

Windows 서버에 Word가 있으면 COM 자동화 품질이 더 높지만, MCP 서버가 Linux면 LibreOffice가 맞다. 사내 변환 서버가 이미 있으면 그걸 재사용한다.

## `.docx`로 갈지, PDF로 갈지

시장품질 `.doc`는 대개 조사서·8D·대책서다. **구조(제목, 표, 리스트)가 중요하면 `.docx`** 가 맞다. Docling HierarchicalChunker를 그대로 쓴다.

PDF로 먼저 보내는 경우는 제한적이다.

- 페이지 레이아웃·스탬프·도장이 의미일 때
- 나중에 페이지 비전 검색(ColPali)을 붙일 때

둘 다 하면 비용만 늘고, 기본은 `.doc → .docx → Docling JSON`이면 된다.

`.xls`는 같은 LibreOffice 게이트가 **1순위가 아니다**. 2026 기준 calamine/polars가 `.xls` 값을 직접 읽는다. LO는 이상한 BIFF·차트 폴백이다. 이후는 벡터가 아니라 Parquet/SQL (`format-pipelines/05-xls.md`). `.ppt`만 `.doc`와 같이 LO 정규화가 1순위다.

## 파이프라인에서의 위치

업로드 직후, Docling 앞에 **정규화 게이트**를 둔다.

```
업로드
  ├─ .doc / .ppt         → LibreOffice → .docx / .pptx
  ├─ .xls                → calamine 직접 (LO는 폴백)
  ├─ 확장자 위조         → 시그니처 기준으로 재분류
  ├─ .docx / .pdf / .md  → Docling
  └─ .xlsx               → calamine → Parquet 1층 (RAG 금지)
```

변환된 `.docx`는 파생 산출물이다. 원본 `.doc`와 `converted_from`, `converter=libreoffice`, `converted_at`을 메타에 남긴다. 나중에 변환기를 바꿔도 재처리할 수 있다.

## 품질 확인 (표본 20개면 충분)

`.doc`가 몇십~몇백 개여도, 변환 품질은 아래만 보면 된다.

1. 변환 성공률
2. 한글 깨짐 여부 (□, `?`, 모지바케)
3. 표 개수: 원본 vs 변환본
4. Heading 스타일이 제목으로 남았는지 (본문만 이어진 통짜 글이면 청킹이 망가짐)
5. 임베디드 엑셀/그림 유실

표가 많이 사라지면 LibreOffice 필터를 `docx:"MS Word 2007 XML"`로 고정하고, 그래도 안 되면 해당 파일만 Word가 있는 Windows에서 재변환하는 예외 경로를 둔다.

## 하지 말 것

- `.doc`를 마크다운으로 바로 덤프해서 청크
- 웹 변환 API에 사내 품질 문서 업로드
- 변환 실패 파일을 빈 문서로 인덱싱
- Docling이 `.doc`를 받는다고 입고 로그에 원본만 남기기 (실패 시 LibreOffice 부재인지, 깨진 파일인지 구분 안 됨)

`.doc`는 포맷 문제가 아니라 **정규화 한 단계**다. 게이트만 잘 두면 이후는 기존 `.docx` 파이프라인과 같아진다.
