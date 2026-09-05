# .dwg 권장 파이프라인

- 배경: 제조 시장품질에서 부품·금형·치공구 AutoCAD 도면(`.dwg`)이 클레임 첨부·8D 증적으로 들어온다. 바이너리 전체를 벡터에 넣지 않는다. 대용량이 흔하다. Docling은 CAD를 파싱하지 않는다.
- 관련 문서: `README.md`, `../market-quality-rag-improvement.md`

## 결론

`.dwg`는 가족 H다. Autodesk **전용 바이너리**다. **ezdxf는 DWG를 네이티브로 못 연다.** Docling·텍스트 추출기·Milvus에 바이트를 넣지 않는다. 검색 가능한 것은 TEXT/MTEXT/속성/레이어명이고, 타이틀 블록은 메타다. 형상은 플롯(PDF/PNG)으로만 본다. 텍스트 1순위는 **ezdwg** 또는 **ODA → DXF → ezdxf**다. LibreDWG만 말하지 않는다.

권장 한 줄:

```
.dwg (원본 보관)
  → 시그니처(AC10xx) · 버전 · 크기
  → ezdwg (R13–R2018) 또는 ODA File Converter → DXF → ezdxf
  → TEXT/MTEXT/ATTRIB/레이어 = 검색 텍스트
  → 타이틀 블록(품번, 도면번호, 개정) = 메타
  → MCP: get_plot / search_text / get_titleblock
  DWG 바이트는 Milvus 금지
```

| 선택 | 판단 |
|---|---|
| DWG 바이트를 Milvus에 넣기 | 하지 말 것 |
| strings / antiword 식 dump | 하지 말 것. 코드와 한글이 섞인다 |
| ezdwg로 DWG 직접 읽기 (R13–R2018) | **텍스트 기본 경로** |
| ODA File Converter → DXF → ezdxf (`odafc`) | **텍스트 기본 경로**. 충실도 최선. 라이선스·외부 프로세스 |
| GNU LibreDWG `dwg2dxf` | 폴백. GPL, 빌드가 자주 아프다 |
| 지정 레이아웃 플롯 → PDF/PNG | **형상 기본 경로** |
| ezdxf로 DWG 네이티브 오픈 | 하지 말 것. DXF만 |
| Docling에 DWG 직접 투입 | 하지 말 것. 미지원 |
| 변환본만 남기고 원본 삭제 | 하지 말 것. 증적 도면 |

## 권장 파이프라인

```
업로드 .dwg
  1. 시그니처
       AC10xx 헤더     → 이 문서
       DXF ASCII/바이너리 → 36-dxf
       %PDF / ZIP / OLE → 재분류 (01 / 컨테이너 / 위조 확장자)
  2. 버전·크기
       헤더 버전 문자열, 파일 크기
       수백 MB면 모델 전체 변환보다 레이아웃 플롯 우선
  3. 텍스트 경로 (둘 중 하나, 병렬 아님)
       A. ezdwg.read — R13–R2018, ezdxf 비슷한 API. 선택 to_dxf
       B. ODA File Converter / ezdxf.addons.odafc → .dxf → ezdxf
       폴백: LibreDWG dwg2dxf — GPL, 컴파일이 자주 실패
       TEXT / MTEXT / ATTRIB / ATTDEF / 치수 문자 / 레이어명
  4. 타이틀 블록
       품번, 도면번호, 개정, 차종, 작성일, 척도
       블록 속성 → 문서 메타. 본문 청크에 반복하지 않음
       ATTRIB가 본이면 ODA→DXF가 더 안전 (ezdwg 커버리지가 아직 얇다)
  5. 플롯
       용지 공간·지정 레이아웃만 PDF 또는 PNG
       큰 파일은 뷰포트 단위. 모델 공간 전체를 래스터하지 않음
  6. 인덱싱
       검색 텍스트 + 타이틀 메타 → 하이브리드
       플롯 이미지 → 01-pdf 또는 17-png-jpeg (OCR/VLM)
       DWG 원본은 오브젝트 스토리지. 벡터 금지
  7. MCP
       get_plot(layout), search_text, get_titleblock
  원본 .dwg 보관. converter, dwg_version, layout_name 메타
```

## 단계별 권장

### 1. 바이트를 임베딩하지 않는 이유

DWG는 엔티티·핸들·프록시 객체의 바이너리다. 임베딩 모델이 형상을 읽지 못한다. 넣으면 용량만 늘고 검색은 깨진다. 가족 H의 원칙은 Visio([33-vsdx.md](33-vsdx.md))와 같다. **도형 텍스트 + 렌더 이미지**다.

시장품질 첨부 DWG는 부품 2D가 많다. 필요한 것은 “무슨 품번 몇 개정인지”, “주기에 뭐라고 적혔는지”, “플롯을 눈으로 볼 수 있는지”다.

### 2. 변환기 우선순위

ezdxf는 DWG를 직접 열지 않는다. DXF만 연다.

1. **ezdwg** (PyPI)  
   DWG R13–R2018(AC1012–AC1032) 읽기. API는 ezdxf와 비슷하다 (`read` / `modelspace` / `query`). 선택 `to_dxf`(ezdxf 백엔드). 외부 변환기 없이 python에서 텍스트를 뽑을 때 1순위다. 엔티티 커버리지는 아직 성장 중이다. TEXT/MTEXT는 되고, 타이틀 블록 `ATTRIB`은 표본으로 확인한다.
2. **ODA File Converter → DXF → ezdxf**  
   충실도가 가장 낫다. `ezdxf.addons.odafc.readfile()`이 변환기를 호출한다. 사내 라이선스/배치가 있으면 그걸 재사용한다. **외부 프로세스 실행은 보안·라이선스 이슈**다. 웹 변환에 사내 도면을 올리지 않는다. 도착 DXF는 [36-dxf.md](36-dxf.md).
3. **플롯기 (AutoCAD / ODA / QCAD 등)**  
   지정 레이아웃을 PDF 또는 PNG로 보낸다. 형상·치수선이 본이면 텍스트만으로 부족하다. PDF면 [01-pdf.md](01-pdf.md), 한 장이면 [17-png-jpeg.md](17-png-jpeg.md).
4. **GNU LibreDWG `dwg2dxf`**  
   폴백이다. GPL이고 빌드가 자주 아프다. 최근 AC 버전은 자주 실패한다. 실패를 성공으로 남기지 않는다. 1순위가 아니다.

R2018 이후·프록시 엔티티·타이틀 블록 속성이 본이면 ODA 쪽이 더 안전하다. ezdwg가 빈 텍스트를 내면 실패로 남기고 ODA로 넘긴다.

### 3. 텍스트와 타이틀 블록

추출 대상은 엔티티 문자다.

- `TEXT`, `MTEXT`
- 블록 속성 `ATTRIB` / `ATTDEF` — 타이틀 블록의 본체
- 치수 문자, 지시선
- 레이어명 — 검색 힌트. 매 청크에 반복 임베딩하지 않음

타이틀 블록은 문서 키가 된다. `품번`, `도면번호`, `개정`, `차종`, `작성일`을 메타 컬럼으로 고정한다. 머리글처럼 모든 청크에 붙여 검색을 오염시키지 않는다. 속성 태그가 영문(`DWG_NO`, `REV`)이어도 매핑 테이블로 한글 키에 맞춘다.

모델 공간 주기와 용지 공간 표제를 섞지 않는다. 표제는 메타, 주기는 검색 텍스트다.

### 4. 대용량과 플롯

DWG는 100MB를 넘는 경우가 흔하다. 모델 공간 전체를 PNG로 찍지 않는다.

- 레이아웃(용지)이 있으면 그것만 플롯한다
- 레이아웃이 없으면 타이틀 블록이 있는 한 뷰만
- 해상도는 읽기용. 인쇄 DPI로 올리지 않는다
- Xref는 경로가 없으면 실패로 남긴다. 빈 플롯을 인덱싱하지 않는다
- 큰 파일은 통째 DXF 변환보다 ezdwg 텍스트 + 레이아웃 플롯이 싸다. 변환이 필요하면 레이아웃만

### 5. MCP

`search` 하나가 아니다. Codex는 표제를 보고 플롯을 연다.

1. `get_titleblock(doc_id)` — 품번, 도면번호, 개정, 레이아웃 목록
2. `search_text(query, filters)` — TEXT/MTEXT/속성. 품번·개정 필터
3. `get_plot(doc_id, layout)` — PDF/PNG 플롯

인용은 `파일명 + 도면번호 + 개정 + 레이아웃`이다.

## 흔한 실패

- DWG를 텍스트 파일처럼 읽어 바이너리가 청크가 된다
- ezdxf에 DWG를 넣어 실패를 “파서 없음”으로만 남긴다
- 신버전 DWG를 LibreDWG에만 넣어 빈 DXF가 “성공”한다
- 타이틀 블록을 본문에 반복해 다른 품번 도면이 같이 검색된다
- 모델 공간 전체를 래스터해 OOM·타임아웃
- Xref 누락 플롯을 정상 도면으로 인덱싱한다
- 원본을 지워 개정 비교·재플롯이 불가능하다
- Docling이 CAD를 받는다고 입고 로그에 원본만 남기기

## 하지 말 것

- DWG 바이트를 Milvus에 넣기
- `strings` / antiword / catdoc로 본문 추출
- ezdxf 네이티브 DWG 오픈을 전제로 짜기
- LibreDWG/ODA만 적고 ezdwg를 빼기
- Docling PDF 파이프라인에 확장자만 바꿔 투입
- 웹 CAD 뷰어에 사내 도면 업로드
- 변환 실패·빈 플롯을 인덱싱
- 원본 삭제

`.dwg`는 문서가 아니라 **도면 컨테이너**다. 텍스트·표제·플롯만 인덱스에 남긴다.

## 인접 포맷

- `.dxf` → [36-dxf.md](36-dxf.md). 교환 포맷. 텍스트 추출이 더 안전하다. ODA/ezdwg `to_dxf`의 도착점.
- `.vsdx` / `.vsd` → [33-vsdx.md](33-vsdx.md). 같은 가족 H. 공정 다이어그램이지 CAD 부품도가 아니다.
- 플롯 `.pdf` → [01-pdf.md](01-pdf.md). 레이아웃 렌더 이후.
- 플롯 `.png` → [17-png-jpeg.md](17-png-jpeg.md). 한 장 도면.
- 표형 첨부 `.xlsx` → [04-xlsx.md](04-xlsx.md). 도면이 아니다. 치수표·BOM이면 C 가족.
