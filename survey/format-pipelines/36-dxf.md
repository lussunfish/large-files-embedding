# .dxf 권장 파이프라인

- 배경: 시장품질 부품 도면의 CAD 교환본(`.dxf`)이다. DWG보다 텍스트에 가깝지만, 평문 `.txt`가 아니다. 가족 H. Docling은 CAD를 파싱하지 않는다.
- 관련 문서: `README.md`, [35-dwg.md](35-dwg.md)

## 결론

`.dxf`는 AutoCAD 교환 포맷이다. ASCII 또는 바이너리다. **ezdxf가 표준이다.** TEXT/MTEXT/속성/레이어/블록을 뽑는다. 대용량 ASCII는 `ezdxf.addons.iterdxf`로 엔티티만 순회한다. 형상 확인이 필요하면 drawing add-on으로 PNG/PDF를 선택적으로 만든다. 그룹 코드가 섞인 원문을 txt처럼 청크하지 않는다. DWG([35-dwg.md](35-dwg.md))의 형제이고, 텍스트 경로는 이쪽이 더 안전하다.

권장 한 줄:

```
.dxf (원본 보관)
  → 시그니처(ASCII 그룹코드 | Binary DXF | 위조 DWG)
  → ezdxf: TEXT / MTEXT / ATTRIB / 레이어 / 블록
  → 대용량 ASCII면 iterdxf (모델공간 이터레이터)
  → 타이틀 블록 = 메타 (품번, 도면번호, 개정)
  → (선택) drawing add-on → PNG/PDF
  → MCP: get_plot / search_text / get_titleblock
  원문을 txt 청크하지 않음
```

| 선택 | 판단 |
|---|---|
| DXF 원문을 `.txt`로 임베딩 | 하지 말 것. 그룹 코드가 본문과 섞인다 |
| ezdxf로 엔티티 텍스트 추출 | **기본 경로** |
| 대용량 ASCII: `ezdxf.addons.iterdxf` | **큰 도면 기본**. 통째 객체화 금지 |
| drawing add-on → PNG/PDF | 선택. 형상·치수선이 본일 때만 |
| DWG 바이너리 파서에 넣기 | 하지 말 것. 포맷이 다름 |
| Docling에 DXF 직접 투입 | 하지 말 것. 미지원 |
| 변환본만 남기고 원본 삭제 | 하지 말 것 |

## 권장 파이프라인

```
업로드 .dxf
  1. 시그니처
       ASCII: 0 / SECTION / HEADER     → 이 문서
       Binary DXF 헤더                 → ezdxf (바이너리 모드)
       AC10xx DWG                      → 35-dwg
       %PDF / ZIP                      → 재분류
  2. ezdxf 파싱
       보통: readfile → modelspace / paperspace / 블록
       대용량 ASCII: ezdxf.addons.iterdxf.opendxf → modelspace() 이터레이터
       TEXT, MTEXT, ATTRIB, ATTDEF
       DIMENSION 문자, 레이어 테이블
  3. 타이틀 블록
       품번, 도면번호, 개정, 차종, 작성일 → 메타
  4. (선택) 플롯
       ezdxf drawing add-on → PNG 또는 PDF
       지정 레이아웃. 기본은 텍스트만
  5. 인덱싱
       검색 텍스트 + 타이틀 메타
       플롯이 있으면 01-pdf / 17-png-jpeg
       DXF 원문 통째 임베딩 금지
  6. MCP
       get_titleblock, search_text, (있으면) get_plot
  원본 .dxf 보관. ascii|binary, acad_version 메타
```

## 단계별 권장

### 1. txt가 아닌 이유

ASCII DXF는 열어 보면 글자가 보인다. 그래서 15-txt로 보내는 실수가 난다. 실제 내용은 그룹 코드다.

```
  0
TEXT
  8
TITLE
  1
A12-34567
```

`0`, `8`, `1` 같은 코드와 좌표(`10`, `20`)가 본문과 같이 임베딩되면 검색이 오염된다. 파서가 엔티티를 고른 뒤 **문자 값만** 남긴다.

바이너리 DXF는 헤더가 `AutoCAD Binary DXF`다. 확장자만 보고 텍스트로 열지 않는다. 진짜 DWG면 [35-dwg.md](35-dwg.md)로 보낸다.

### 2. ezdxf가 본체다

시장품질 DXF는 2D 부품도가 많다. ezdxf로 아래만 모으면 검색은 된다.

- `TEXT`, `MTEXT` — 주기, 공차, 주석
- 블록 속성 — 타이틀 블록
- 레이어명 — 필터·힌트
- `INSERT` 블록명 — 표준 부품 기호

좌표·핸들·프록시 바이너리는 버린다. 3D 메쉬를 문장으로 만들지 않는다.

큰 ASCII DXF는 `ezdxf.readfile`이 문서 전체를 메모리에 올린다. **`ezdxf.addons.iterdxf`**로 모델공간 엔티티만 한 개씩 읽는다. 수 GB급·메모리에 안 들어가는 도면용이다. ASCII만 된다. 바이너리 DXF는 iterdxf가 아니다.

```python
from ezdxf.addons import iterdxf

doc = iterdxf.opendxf("huge.dxf")
try:
    for e in doc.modelspace():
        if e.dxftype() in ("TEXT", "MTEXT", "ATTRIB", "ATTDEF"):
            ...
finally:
    doc.close()
```

ODA 경유는 DXF가 이미 있으면 필요 없다. DWG에서 온 파생 DXF면 `converted_from=dwg`를 유지한다.

### 3. 타이틀 블록과 청크

표제는 DWG와 같다. 품번·도면번호·개정은 메타다. 본문 주기와 합쳐 한 청크로 만들지 않는다.

검색 텍스트는 레이어 또는 용지 공간 단위로 묶는다. 파일 전체를 한 blob으로 dump 하지 않는다. Visio([33-vsdx.md](33-vsdx.md))의 “셰이프 텍스트”와 같은 생각이다.

한글 깨짐은 코드 페이지다. `$DWGCODEPAGE` / 파일 인코딩을 보고, `□`이면 인덱싱하지 않고 실패로 남긴다.

### 4. 플롯은 선택이다

DXF는 텍스트 추출이 DWG보다 안전하다. 그래서 플롯이 기본이 아니다.

플롯을 만드는 경우:

- 치수선·단면 기호가 문자로 안 나올 때
- 검토자가 도면을 봐야 할 때
- 배포본이 이미 플롯 PDF일 때 — 그때는 [01-pdf.md](01-pdf.md)

python 기본은 **ezdxf drawing add-on**이다. `pip install ezdxf[draw]`. matplotlib 또는 PyMuPDF 백엔드로 PNG/PDF/SVG. CLI는 `ezdxf draw -o out.png file.dxf`. AutoCAD/ODA 플롯기는 필수가 아니다.

둘 다 기본으로 돌리면 대용량에서 비용만 는다. MCP `get_plot`은 플롯이 있을 때만 응답한다. 모델 공간 전체를 인쇄 DPI로 찍지 않는다.

### 5. MCP

도구 세트는 35와 맞춘다. 교환본이라고 도구를 줄이지 않는다.

1. `get_titleblock(doc_id)`
2. `search_text(query, filters)` — 레이어 필터 가능
3. `get_plot(doc_id, layout)` — 산출물이 있을 때

인용은 `파일명 + 도면번호 + 개정`이다.

## 흔한 실패

- DXF를 `.txt`로 읽어 그룹 코드가 청크가 된다
- 바이너리 DXF를 utf-8로 열어 빈 문서가 된다
- 위조 확장자 DWG를 ezdxf에 넣는다
- 대용량 ASCII를 `readfile`로 통째 로드해 OOM
- 타이틀 속성을 본문에 붙여 품번 검색이 전 도면에 맞는다
- 전체 좌표 리스트를 임베딩해 토큰만 소모한다
- 한글 코드 페이지를 무시해 품번이 `????`가 된다
- Docling이 CAD를 받는다고 입고 로그에 원본만 남기기

## 하지 말 것

- 원문 dump 후 토큰 윈도우 자르기
- `grep`으로 품번만 뽑아 파일 전체를 인덱싱했다고 보기
- Docling·마크다운 경로에 넣기
- 웹 변환에 사내 도면 업로드
- 원본 삭제
- DWG와 다른 MCP를 대충 `search` 하나로 끝내기

`.dxf`는 “글자가 보이는 CAD”일 뿐, 메모장이 아니다.

## 인접 포맷

- `.dwg` → [35-dwg.md](35-dwg.md). 바이너리 선행. 이 문서가 텍스트 도착점인 경우가 많다.
- `.vsdx` → [33-vsdx.md](33-vsdx.md). 같은 가족 H. 공정 흐름도.
- 플롯 `.pdf` → [01-pdf.md](01-pdf.md)
- 서술 보고서 `.hwp` → [09-hwp.md](09-hwp.md). 도면이 아니다. 첨부 DXF가 있으면 이 문서로 재분기.
- BOM·치수표 `.xlsx` → [04-xlsx.md](04-xlsx.md). 가족 C. 도면 엔티티가 아니다.
