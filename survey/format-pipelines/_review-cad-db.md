# CAD / Access 파이프라인 리뷰 (2026-09)

대상: `31-accdb.md` `32-mdb.md` `33-vsdx.md` `34-vsd.md` `35-dwg.md` `36-dxf.md`. 패치는 원문에 반영했다. 체언은 하다/다.

공통으로 맞춘 사실: **Docling은 visio / cad / access를 파싱하지 않는다.** 확장자만 바꿔 StandardPdfPipeline에 넣지 않는다.

README 한 줄(가족 C/H)은 방향이 같아서 손대지 않았다.

## 31-accdb.md

**문제.** Linux 도구를 `mdbtools / Access ODBC / access-parser`로만 적었다. `access-parser`를 기본처럼 두면 100MB급이 파일 전체를 메모리에 올린다. 암호 DB는 “실패 큐”만 있고, mdb-json·polars·pyaccdb·Jackcess가 없다. Docling 미지원이 약하다.

**패치.**

- Linux 표준은 그대로 **mdbtools** (`mdb-tables`, `mdb-schema`, `mdb-export`, **`mdb-json`**).
- `polars_access_mdbtools`를 1층 Parquet 선택지로 넣었다.
- Windows는 ACE ODBC.
- 암호 ACE는 **pyaccdb**(2025, Agile Encryption, 페이지 단위) / **Jackcess Encrypt**(Java). 암호는 시크릿만. 로그·청크 금지. 없으면 실패 큐.
- `access_parser`는 파일 전체 로드·암호 미지원. 대용량 금지로 강등.
- SQL 2층, 행 RAG 금지는 유지.

## 32-mdb.md

**문제.** mdbtools가 본체라는 판단은 맞다. `mdb-json`·`polars_access_mdbtools`가 없고, `access_parser`를 “ACE 위주”로만 적었다. 대용량 로드 위험이 빠져 있다.

**패치.**

- export에 `mdb-json`을 추가. 테이블 단위 유지.
- `polars_access_mdbtools`는 선택.
- `access_parser`는 Jet 기본이 아니고 파일 전체 로드. 대용량 금지.
- 한글 cp949, `.ldb` 복사, 이후 31과 동일, SQL not RAG는 유지.
- Docling 미지원을 명시.

## 33-vsdx.md

**문제.** ZIP+XML·셰이프 텍스트·페이지 렌더는 맞다. 그런데 파서 이름이 없다. 일반 zip(30) / XML(19) 금지만 있고, `vsdx` 라이브러리와 LangChain `VsdxParser` 구분이 없다. Docling은 “PDF 파이프라인에 직접” 정도로만 막았다.

**패치.**

- 기본 파서는 python **`vsdx`(dave-howard/vsdx)**. 페이지별 `Shape.text`.
- LangChain `VsdxParser`는 ZIP XML dump. 셰이프 단위가 아니다. 차선.
- 일반 zip으로 풀어 미디어만 흩뿌리지 말 것.
- 페이지 렌더는 LibreOffice/Visio, PDF면 01.
- **Docling은 vsdx를 파싱하지 않는다.**

## 34-vsd.md

**문제.** “직접 파싱하지 말고 vsdx/PDF로 변환”은 맞다. 변환 엔진이 LibreOffice/Visio만 있고 **libvisio**가 없다. `vsd2text`를 기본으로 오해할 여지가 있다. python `vsdx`에 OLE를 넣는 실패는 한 줄뿐이다.

**패치.**

- 변환 엔진은 **LibreOffice(libvisio)** 또는 Visio COM. 도착은 vsdx 우선, PDF 보조.
- `vsd2text`/`vsd2xhtml`는 라벨만, 커넥터 유실. 기본이 아니다.
- python `vsdx`는 `.vsdx` 전용. OLE vsd 투입 금지.
- Docling 미지원을 명시.

## 35-dwg.md

**문제.** “ODA → DXF, 또는 플롯 / LibreDWG 폴백”만 있다. **ezdxf가 DWG를 네이티브로 못 연다**는 사실은 있으나, 1순위가 ODA·LibreDWG로만 읽힌다. 2026-09 **ezdwg**가 빠져 있다.

**패치.** 텍스트 1순위는 둘이다. LibreDWG만 말하지 않는다.

1. **ezdwg** (PyPI, API는 ezdxf와 비슷, DWG R13–R2018 읽기, 선택 `to_dxf`).
2. **ODA File Converter → DXF → ezdxf** (`ezdxf.addons.odafc`). 충실도 최선. 라이선스·외부 프로세스 보안.
3. **GNU LibreDWG `dwg2dxf`**. 폴백. GPL, 빌드가 자주 아프다.

- 타이틀 블록 `ATTRIB`은 ezdwg 커버리지가 아직 얇다. 표제가 본이면 ODA→DXF.
- 형상은 레이아웃 플롯. 모델 공간 전체 래스터 금지.
- Docling 미지원.

## 36-dxf.md

**문제.** ezdxf가 본체라는 판단은 맞다. 대용량을 “엔티티 이터레이터”로만 적어서 **`iterdxf` 이름이 없다.** 플롯기만 있고 **drawing add-on**이 없다.

**패치.**

- ezdxf는 그대로 표준.
- 대용량 ASCII는 **`ezdxf.addons.iterdxf`**. 모델공간 한 엔티티씩. ASCII만. 바이너리 DXF는 해당 없음.
- 선택 플롯은 **drawing add-on** (`ezdxf[draw]`, PNG/PDF/SVG). AutoCAD/ODA 플롯기는 필수 아님.
- Docling 미지원.

## 유지한 것

- 가족: accdb/mdb = C (SQL, 행 RAG 금지). vsdx/vsd/dwg/dxf = H (도형 텍스트 + 렌더, 바이너리 임베딩 금지).
- 시그니처 재분류, 원본 보관, 웹 변환 API 금지, MCP를 `search` 하나로 끝내지 않기.
- 목차: 결론 / 권장 파이프라인 / 단계별 / 흔한 실패 / 하지 말 것 / 인접 포맷.

## 출처 (2026-09)

- ezdwg 0.12.7 PyPI, R13–R2018, `to_dxf`. https://pypi.org/project/ezdwg/
- ezdxf 1.4.4: DWG 네이티브 없음, `odafc`, `iterdxf`(ASCII), drawing add-on.
- vsdx: dave-howard/vsdx. LangChain `VsdxParser`는 ZIP XML.
- Docling supported formats: visio/cad/access 없음. https://docling-project.github.io/docling/usage/supported_formats/
- mdbtools: `mdb-json` 포함. `polars_access_mdbtools` 래퍼.
- pyaccdb (2025-11): ACE + Agile Encryption. access_parser는 전체 로드.
- Jackcess Encrypt: 암호 accdb Java.
- libvisio: LibreOffice vsd 임포트 엔진.
