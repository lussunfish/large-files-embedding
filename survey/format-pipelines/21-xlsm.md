# XLSM 권장 파이프라인

- 배경: 시장품질 RAG/MCP에서 매크로 사용 통합문서(`.xlsm`, 가족 C)를 어떻게 넣을 것인가. 약 3,100건 코퍼스, 단일 파일 최대 ~100MB. 값은 SQL, VBA는 실행하지 않는다.
- 관련 문서: `../excel-to-sql-decision.md`, `../xlsx-20-samples-layer1.md`, `README.md`

## 결론

`.xlsm`은 `.xlsx`와 같은 OOXML이다. 차이는 `xl/vbaProject.bin`뿐이다. **calamine은 값만 읽고 VBA는 무시한다.** 매크로는 켜지 않는다. 바이너리 VBA를 인덱싱하지 않는다. 신뢰하지 않는 코드로 취급한다.

| 선택 | 판단 |
|---|---|
| VBA/매크로 활성화·실행 | 하지 말 것. 비신뢰 코드 |
| `vbaProject.bin`을 Milvus/카탈로그에 | 하지 말 것 |
| 행을 텍스트 청크로 임베딩 | 하지 말 것 |
| fastexcel/calamine로 값만 추출(VBA 무시) → Parquet | **기본 경로** |
| 값 추출 실패 → LibreOffice → xlsx 후 04 | 폴백. 매크로는 제거됨 |
| 메타에 `has_macro=true` | 해야 함 |
| 파일마다 SQL 테이블 | 하지 말 것 |
| 100MB를 openpyxl 전체 로드 | 하지 말 것. 스트리밍 |

권장 한 줄:

```
.xlsm → 시그니처(ZIP/OOXML) → 매크로 비활성 → fastexcel/calamine 값 추출(VBA 무시)
      → Parquet 1층 → SQL 2층 (04와 동일)
      → has_macro=true. vbaProject.bin 인덱싱 금지. 벡터에는 카탈로그만. VBA 실행 금지
```

## 권장 파이프라인

```
업로드 .xlsm (~100MB 가능)
  1. 시그니처
       ZIP/OOXML + xl/vbaProject.bin → 진짜 xlsm
       ZIP인데 vba 없으면 확장자만 잘못된 xlsx. 04
       OLE(D0 CF)                   → 05-xls 게이트
  2. 보안 게이트
       매크로 엔진 비활성. Excel/LibreOffice에서 Enable 금지
       vbaProject.bin 은 존재만 기록, 내용 미파싱
  3. 값 추출 (기본)
       polars read_excel(engine=calamine) / fastexcel
       셀 값만. VBA는 무시·미실행
  4. 폴백
       엔진이 거부하면 soffice --headless --convert-to xlsx
       변환본은 매크로가 빠진 파생물. 원본 xlsm 보관
  5. 이후는 04-xlsx
       시트 인벤토리 → 프로파일 JSON → Parquet 1층 → SQL 2층
  6. 메타
       has_macro=true, converted_from=xlsm (폴백 시)
       피벗/차트/매크로 시트는 데이터로 적재하지 않음
  7. MCP
       list_tables / describe_table / query_tables (읽기 전용)
       벡터에는 카탈로그만. 행 임베딩 금지
```

원본 `.xlsm`을 보관한다. 변환 xlsx는 파생물이다. Codex CLI가 파일을 열 때도 매크로를 실행하지 않는다.

## 단계별 권장

### 1. 값은 xlsx, 코드는 버린다

calamine/python-calamine과 Polars `read_excel`(기본 엔진 calamine)은 xlsm의 **값만** 읽는다. VBA는 무시한다. 실행하지 않는다. 이 경로가 되면 LibreOffice를 타지 않는다. 100MB면 시트 단위 스트리밍이다. openpyxl `load_workbook` 전체 로드는 04와 같이 금지한다.

`keep_vba=True`로 저장·재기록하지 않는다. 입고는 읽기 전용이다.

### 2. 매크로는 존재 플래그만

```text
has_macro=true
macro_artifact=xl/vbaProject.bin
macro_executed=false
```

VBA 모듈을 디컴파일해 청크하지 않는다. Auto_Open / Workbook_Open이 있어도 파이프라인이 Excel을 띄우지 않으면 실행되지 않는다. 변환·파싱 워커에 Excel COM을 쓰지 않는 이유다.

LibreOffice 폴백은 `xlsx`로 보내 매크로를 떨어뜨린다. 값은 남고 코드는 사라진다. C 가족은 셀 값이 본체다.

### 3. 이후는 04와 완전히 같다

파일당 테이블 금지. 원본 컬럼 유지. 월보 스냅샷은 UNION하지 않는다. `source_file`, `sheet_name`, `report_period`, `ingested_at`. 원인/대책 긴 칸은 SQL에서 지우지 않고 RAG로만 복제한다. 3,100건을 채팅에 올리지 않는다. 프로파일 JSON 20개로 스키마를 맞춘다.

### 4. 보안

시장품질 공유 폴더의 xlsm은 외부 협력사 파일이 섞인다. 매크로를 신뢰하지 않는다. 샌드박스에서 열더라도 Enable Macros를 켜지 않는다. `vbaProject.bin`을 다른 호스트에서 실행하거나, 추출 스크립트를 `cmd`/`powershell`로 돌리지 않는다.

## 흔한 실패

- Excel에서 매크로를 켠 채 열어 입고 서버가 코드를 실행한다
- `vbaProject.bin`을 바이너리 청크로 Milvus에 넣는다
- openpyxl로 100MB xlsm을 통째 로드해 OOM
- 값 시트를 못 읽어 빈 문서로 인덱싱한다
- 변환 xlsx만 남기고 원본 xlsm 경로를 잃는다
- 행을 임베딩해 “비슷한 클레임”을 벡터로 찾는다. 집계가 틀린다
- `has_macro`를 안 남겨 나중에 감사 추적이 안 된다

## 하지 말 것

- VBA 실행, Auto_Open 허용, COM 자동화로 매크로 돌리기
- xlsm을 마크다운 표로 바꿔 Milvus
- 웹 변환 API에 사내 원장 업로드
- 변환 실패 파일을 빈 Parquet로 적재
- 원본 `.xlsm` 삭제
- `SELECT *`를 Codex에 열어 두기

## 인접 포맷

- `.xlsx` → [04-xlsx.md](04-xlsx.md). 이 문서의 도착점. 매크로만 없다
- `.xls` → [05-xls.md](05-xls.md). OLE면 그쪽 게이트. 매크로는 버려도 됨
- `.xlsb` → [22-xlsb.md](22-xlsb.md). BIFF12. openpyxl 불가
- `.csv` → [06-csv.md](06-csv.md). 매크로 없음. 바로 Parquet
- `.docm` → [27-docm.md](27-docm.md). 같은 “매크로 버리고 본문만” 규칙, 가족 A
