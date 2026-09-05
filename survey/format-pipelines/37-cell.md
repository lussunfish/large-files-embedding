# .cell 권장 파이프라인

- 배경: 한국 제조 시장품질 업무에서 한셀(`.cell`)은 한글(`.hwp`)과 같이 한컴 오피스로 도는 스프레드시트다. 클레임 원장·월보·검사 대장이 xlsx 대신 이 확장자로 온다.
- 관련 문서: `README.md`, `../excel-to-sql-decision.md`, [09-hwp.md](09-hwp.md), [04-xlsx.md](04-xlsx.md)

## 결론

`.cell`은 가족 C다. 한컴 스프레드시트다. **Docling은 `.cell`을 파싱하지 않는다.** HWP/HWPX와 같다. 한컴오피스로 `.xlsx`로 바꾼 뒤 [04-xlsx.md](04-xlsx.md)를 탄다. LibreOffice 필터는 있을 때만, 그리고 검증 전제다. antiword 식 텍스트 추출은 쓰지 않는다. 원본은 보관한다. 한글 벤더 우선 순서는 `.hwp`와 같다. hwpkit/syhwp는 셀 포맷이 아니다.

권장 한 줄:

```
.cell (원본 보관)
  → 시그니처 확인
  → (우선) 한컴오피스 / 한셀 공식 변환 → .xlsx
  → (차선) LibreOffice CELL 필터 — 있으면, 검증 필수
  → 04-xlsx (calamine/polars → Parquet 1층 → SQL 2층)
  벡터 금지. antiword 금지. Docling 직접 투입 금지
```

| 선택 | 판단 |
|---|---|
| Docling에 `.cell` 직접 투입 | 하지 말 것. 네이티브 파싱 없음 |
| 한컴 공식 변환 → xlsx 후 04 | **기본 경로** |
| LibreOffice CELL 필터 → xlsx | 차선. 필터·한글·병합을 검증 |
| hwpkit / syhwp / pyhwp | 하지 말 것. 한글 문서용이다 |
| antiword / strings / catdoc dump | 하지 말 것 |
| 변환 후 Milvus 청크 | 하지 말 것. 여전히 정형 |
| 변환본만 남기고 원본 삭제 | 하지 말 것 |

## 권장 파이프라인

```
업로드 .cell
  1. 시그니처
       한셀 패키지/바이너리 → 이 문서
       PK (ZIP/OOXML)      → 확장자만 잘못된 xlsx. 이름만 고치고 04
       D0 CF 11 E0 (OLE)   → 레거시 xls 가능성. 05와 한셀을 구분
       HWP 헤더            → 09-hwp. 확장자 위조
  2. 변환기 선택 (위에서 아래로)
       한컴오피스 자동화 / 한셀 공식 변환
       LibreOffice + CELL import 필터 (있으면)
  3. 검증
       시트 수, 데이터 행 수, 한글 깨짐, 헤더 잔존
  4. 이후는 04-xlsx
       스트리밍 → Parquet 1층 → 표준 팩트 SQL 2층
       파일당 테이블 금지. 피벗/차트 시트 스킵
  5. 메타
       converted_from=cell, converter=hancom|libreoffice
  원본 .cell 보관
```

## 단계별 권장

### 1. 왜 Docling·엑셀 파서에 바로 넣지 않는가

한셀은 xlsx가 아니다. 한컴 전용 구조다. openpyxl·calamine·Docling은 이 확장자를 표로 읽지 못한다. “스프레드시트니까 04”가 아니라, **먼저 xlsx로 정규화**한다.

한글(`.hwp`)과 같은 벤더다. 변환기 우선순위도 같다. 한컴이 있으면 한컴이 표·병합·한글을 가장 잘 살린다. 사내 변환 서버가 한글용으로 있으면 한셀도 같은 워커에 태운다. hwpkit·syhwp는 HWP/HWPX용이다. `.cell`에 쓰지 않는다.

웹 변환 API에 사내 원장을 올리지 않는다.

### 2. 변환기 우선순위

1. **한컴오피스 / 한셀 공식 변환**  
   Windows에 한컴이 있으면 COM·배치 변환이 기본이다. 도착은 `.xlsx`다. `.xls`나 CSV로 내리면 날짜·한글이 한 번 더 깨진다.
2. **LibreOffice CELL 필터**  
   필터가 설치된 이미지에서만 시도한다. 없는 컨테이너가 많다. 있어도 병합 셀, 한글 폰트, 여러 시트가 빠지는 경우가 있다. 성공 로그보다 시트·행 수 비교가 본이다.
3. **텍스트 dump**  
   쓰지 않는다. antiword·catdoc·strings는 표를 문장으로 붕괴시킨다.

LibreOffice는 한글 폰트(`fonts-noto-cjk` / `fonts-nanum`)가 없으면 변환은 성공해도 셀이 `□□`가 된다. soffice 동시 실행은 약하다. 워커 하나 또는 파일마다 `UserInstallation`. 타임아웃을 건다. issue #3819와 같다.

### 3. 변환 후는 완전히 04다

한셀이라고 RAG를 타지 않는다. 숫자는 SQL, 서술은 칸을 복제할 때만 RAG다.

- calamine/polars 스트리밍. openpyxl 전체 로드 금지
- Parquet 1층, 원본 컬럼 유지
- 공통 팩트만 SQL 2층. 파일당 테이블 금지
- 월보 스냅샷은 `source_file` + `report_period`. UNION 금지
- MCP: `list_tables` / `describe_table` / `query_tables`
- 벡터에는 카탈로그만. 원인/대책 긴 칸은 테이블에서 삭제하지 않음

1층 랜딩 포맷은 이 프로젝트의 Parquet다. 변환 xlsx를 다시 `.cell`로 돌리지 않는다.

### 4. 검증

표본이 적어도 아래면 게이트를 고정한다.

1. 변환 성공률
2. 시트 수·데이터 행 수 (한셀 vs xlsx)
3. 한글 깨짐 (`□`, `?`, 모지바케)
4. 헤더 행 위치
5. 차트시트 유실 — C 가족에서는 허용. 값 시트가 비면 실패

빈 통합문서를 04에 넘기지 않는다.

## 흔한 실패

- Docling이 “문서를 받는다”고 `.cell`을 PDF/HTML 경로에 넣는다
- openpyxl로 `.cell`을 열어 즉시 실패하거나 빈 표를 적재한다
- LibreOffice 필터 없는 컨테이너에서 변환 “성공”, 실제는 빈 xlsx
- 한글 폰트 없이 변환해 품번이 `????`
- 변환 후 행을 Milvus에 넣어 집계가 틀린다
- 원본을 지워 한컴 재변환이 불가능하다

## 하지 말 것

- antiword / catdoc / 임의 바이너리 strings로 본문 추출
- `.cell` → CSV 텍스트 → 임베딩
- 마크다운 표 dump 후 토큰 자르기
- 변환 실패를 빈 Parquet로 적재
- 원본 삭제
- 사내 품질 원장을 외부 웹 변환에 업로드
- 파일마다 SQL 테이블 생성

`.cell`은 포맷 문제가 아니라 **한컴 → xlsx 정규화 한 단계**다. 게이트만 두면 이후는 04와 같다.

## 인접 포맷

- `.xlsx` → [04-xlsx.md](04-xlsx.md). 이 문서의 도착점.
- `.xls` → [05-xls.md](05-xls.md). 같은 “레거시 → xlsx” 게이트. 벤더는 한컴이 아니다.
- `.hwp` / `.hwpx` → [09-hwp.md](09-hwp.md), [10-hwpx.md](10-hwpx.md). 같은 한컴 우선 변환. 도착은 서술 가족 A. Docling은 여기도 파싱하지 않는다.
- `.show` → [38-show.md](38-show.md). 한쇼. 도착은 슬라이드 07.
- 1층 `.parquet` → [40-parquet.md](40-parquet.md). 변환 이후 랜딩.
- 도면 `.dwg` → [35-dwg.md](35-dwg.md). 표가 아니다.
