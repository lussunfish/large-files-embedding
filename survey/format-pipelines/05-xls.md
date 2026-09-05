# XLS 권장 파이프라인

- 배경: 시장품질 레거시 `.xls`(BIFF 8 / OLE)는 openpyxl이 못 읽는다. calamine/polars는 `.xls`를 직접 읽는다. LibreOffice 변환은 폴백이다.
- 관련 문서: `../excel-to-sql-decision.md`, `../xlsx-20-samples-layer1.md`, `README.md`

## 결론

`.xls`는 calamine/polars가 직접 읽는다. 시그니처를 확인하고 값만 뽑아 **04-xlsx와 같은 Parquet 1층**으로 간다. LibreOffice는 이상한 BIFF·차트 폴백이다. 임베디드 차트는 버려도 된다. C 가족은 셀 값이 본체다.

| 선택 | 판단 |
|---|---|
| openpyxl로 `.xls` 읽기 | 하지 말 것. OOXML 전용 |
| xlrd 2.x로 BIFF 읽기 | 하지 말 것. 2.0+는 xlsx만 |
| xlrd 1.2를 입고 기본으로 | 하지 말 것. 유지보수 단절 |
| calamine/polars `read_excel` 직접 읽기 | **기본 경로** |
| LibreOffice → xlsx 후 04 | 폴백. 이상한 BIFF·차트 |
| 변환본만 남기고 원본 삭제 | 하지 말 것 |
| 변환 후 Milvus 청크 | 하지 말 것. 여전히 정형 |
| 임베디드 차트·VBA 복원 | 필요 없음. C 가족은 숫자 |

권장 한 줄:

```
.xls → 시그니처(BIFF vs 위조 xlsx) → calamine/polars 직접 읽기
     → Parquet 1층 → SQL 2층 (04와 동일). 벡터 금지
     → 실패·이상한 BIFF/차트만 LibreOffice → xlsx
```

## 권장 파이프라인

```
업로드 .xls
  1. 시그니처
       D0 CF 11 E0  → BIFF/OLE → calamine
       PK (ZIP)     → 확장자만 잘못된 xlsx. 이름만 고치고 04
       XML          → SpreadsheetML 등. 19로 재분류
  2. 값 추출 (기본)
       polars read_excel(engine=calamine) / python-calamine
       시트 단위. xlrd·openpyxl 금지
  3. 폴백
       깨진 BIFF·차트만 soffice --headless --convert-to xlsx
       원본 보관 + converted_from 메타
       한글 점검. □, ?, 모지바케면 폰트·필터 재시도
  4. 이후는 04-xlsx
       Parquet 1층 → SQL 2층
       파일당 테이블 금지. 피벗/차트 시트 스킵
  5. 손실 허용
       임베디드 차트·매크로·VBA는 버려도 됨
       C 가족은 셀 값이 본체다
  6. MCP
       list_tables / describe_table / query_tables (읽기 전용)
       벡터에는 카탈로그만. 원인/대책은 RAG 복제, 삭제 금지
```

## 단계별 권장

### 1. 확장자를 믿지 않는다

`.xls`인데 실제로는 xlsx인 파일이 흔하다. 잘못된 파일을 05·LibreOffice에 넣으면 실패 원인 추적이 어렵다.

```bash
file claim_ledger.xls
# Composite Document File V2 / Excel 97-2003  → 변환
# Microsoft Excel 2007+ / Zip archive         → 04로 바로
```

시그니처가 ZIP이면 확장자만 고친다. BIFF가 아니면 05를 타지 않는다.

### 2. 기본은 calamine, LibreOffice는 폴백

python-calamine / Polars `read_excel`(기본 엔진 calamine)은 `.xls`를 직접 읽는다. pandas 3.1 `engine='calamine'`도 같다. 변환 없이 04와 같은 Parquet 1층으로 간다.

LibreOffice는 깨진 BIFF, 차트시트만 있는 파일, calamine이 거부하는 경우에만 탄다.

```bash
soffice --headless --norestore --nolockcheck \
  --convert-to xlsx:"Calc MS Excel 2007 XML" \
  --outdir /data/normalized \
  claim_ledger.xls
```

- 한글 폰트(`fonts-noto-cjk` / `fonts-nanum`)를 컨테이너에 넣는다. 없으면 변환은 성공해도 셀이 `□□`가 된다
- soffice는 동시 실행에 약하다. 워커 하나, 또는 파일마다 별도 `UserInstallation`
- 타임아웃을 건다. 깨진 BIFF가 soffice를 붙잡는다
- 실패는 `failed_xls`로 남기고 배치를 멈추지 않는다
- 원본 `.xls`와 `converter=calamine|libreoffice`, `converted_at`을 메타에 남긴다

xlrd 1.2는 BIFF를 읽지만 날짜·한글·병합에서 깨지기 쉽다. 입고 기본 경로로 쓰지 않는다. pandas `read_excel(engine='xlrd')`도 같다.

### 3. 추출·변환 후 한글·숫자 검증

표본 20개면 calamine 추출과(폴백이면) 변환 품질을 고정할 수 있다.

1. calamine 성공률. 실패만 LibreOffice
2. 셀 한글 깨짐 (`□`, `?`, 모지바케)
3. 사용 시트 수·데이터 행 수 (원본 vs 추출/xlsx)
4. 날짜가 시리얼로 남았는지
5. 차트시트 유실 — 허용한다

차트는 C 가족에서 복원할 필요가 없다. 숫자는 셀에 있다. 차트만 있고 값 시트가 비면 실패로 남긴다.

### 4. 이후는 04와 완전히 같다

xls·변환 xlsx를 Docling에 넣지 않는다. Parquet 1층, 원본 컬럼 유지, 파일당 테이블 금지, 스트리밍, 스냅샷이면 `source_file`·`report_period`. MCP는 읽기 전용 세 도구다. 원인/대책 긴 칸은 테이블에서 지우지 않는다. Docling XLS 경로는 LibreOffice 변환 후 openpyxl이라 SQL 경로에 맞지 않는다.

## 흔한 실패

- openpyxl `load_workbook('a.xls')` → 즉시 실패 또는 잘못된 파싱
- calamine이 읽는데도 무조건 LibreOffice로 보내 변환 대기열이 는다
- 위조 xlsx를 LibreOffice에 넣어 원인 불명 오류
- 변환 후 한글 셀이 `????`. 컨테이너에 CJK 폰트 없음
- xlrd 2.x로 BIFF를 열려고 함
- 변환 성공을 품질 성공으로 착각. 시트 행 수를 안 비교함
- 변환본만 인덱싱하고 원본 경로를 잃어 재처리가 안 됨

## 하지 말 것

- `.xls`를 텍스트 추출(`ssconvert` 텍스트 모드, catdoc 계열) 후 임베딩
- 웹 변환 API에 사내 원장 업로드
- 변환 실패 파일을 빈 Parquet로 적재
- 차트 복원을 위해 PDF 경로로 우회
- 원본 `.xls` 삭제
- 변환 후 파일마다 SQL 테이블 생성

## 인접 포맷

- `.xlsx` → 변환 없이 04
- `.csv` → 06. LibreOffice 불필요
- `.xlsb` → [22-xlsb.md](22-xlsb.md). 같은 calamine 기본
- `.doc`/`.ppt` → LibreOffice 게이트. 결과는 서술/슬라이드 가족. xls와 다름
- SpreadsheetML XML → 19에서 표형 XML로 분류 후 flatten
- 암호 걸린 통합문서 → 실패 큐. 암호를 파이프라인에 넣지 말 것
