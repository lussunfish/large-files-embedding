# Access MDB 권장 파이프라인

- 배경: 시장품질 레거시 클레임 원장이 Jet Access(`.mdb`, 97–2003)로 남아 있는 경우가 많다. Linux에서는 mdbtools가 본체다. 한글은 cp949다. Docling은 Access를 파싱하지 않는다.
- 관련 문서: `../excel-to-sql-decision.md`, `README.md`

## 결론

`.mdb`는 가족 C다. Outlook `.msg`와 같은 OLE여도 메일이 아니다. mdbtools로 테이블을 내보낸 뒤 **31-accdb**와 같다. 파일을 RAG하지 않는다. 인코딩을 먼저 고정한다.

| 선택 | 판단 |
|---|---|
| mdb 바이너리를 Milvus에 넣기 | 하지 말 것 |
| OLE라서 11-msg로 보내기 | 하지 말 것. 메일이 아님 |
| mdbtools export → Parquet → SQL | **기본 경로** |
| polars_access_mdbtools | 선택. Parquet 1층과 맞으면 |
| 인코딩 utf-8만 가정 | 하지 말 것. 기본은 cp949 |
| access_parser로 Jet/대용량 로드 | 하지 말 것. ACE 위주, 파일 전체 로드 |
| 이후 경로를 31과 다르게 | 하지 말 것 |
| 폼·VBA·리포트 인덱싱 | 하지 말 것 |
| Access가 연 상태에서 직접 읽기 | 하지 말 것. 잠금 |
| Docling에 mdb 투입 | 하지 말 것. 미지원 |

권장 한 줄:

```
.mdb → 시그니처(Jet OLE, MSG 아님) → 잠금이면 복사
     → mdbtools (mdb-tables/mdb-schema/mdb-export/mdb-json, cp949)
     → (선택) polars_access_mdbtools
     → 31과 동일. Parquet 1층 → SQL 2층. 벡터에는 카탈로그만
```

## 권장 파이프라인

```
업로드 .mdb
  1. 시그니처
       OLE CFB (D0 CF 11 E0)
       Jet/Access → 이 문서
       Outlook → 11-msg. Word → 03. Excel → 05
       ACE(.accdb)인데 이름만 mdb → 31
  2. 잠금
       Access가 열어 두면 .ldb
       복사본을 읽고 원본은 그대로
  3. mdbtools 인벤토리
       mdb-ver / mdb-tables / mdb-schema
       MSys* 스킵. 폼·쿼리·리포트는 메타만
  4. 테이블 export
       mdb-export -Q -D '%Y-%m-%d'  또는  mdb-json
       인코딩 cp949 (실패 시 euc-kr / utf-8)
       (선택) polars_access_mdbtools → DataFrame → Parquet
  5. 이후는 31-accdb
       Parquet 1층 → 관계 카탈로그 → SQL 2층
       MCP list_tables / describe_table / query_tables
```

## 단계별 권장

### 1. OLE를 메일·엑셀과 섞지 않는다

`.mdb`·`.msg`·`.doc`·`.xls`는 모두 `D0 CF 11 E0`이다. 확장자만 보면 클레임 원장이 메일 파이프라인으로 간다.

```bash
file claim_ledger.mdb
# Microsoft Access Database / Jet DB  → 32
# Microsoft Outlook message           → 11
# Composite Document File V2          → mdb-ver / oleid로 한 번 더
```

`mdb-ver`가 Jet 3/4를 말하면 여기다. ACE면 확장자를 고치고 [31-accdb.md](31-accdb.md)로 보낸다. 암호 MDB는 실패 큐다. (Jackcess Encrypt는 Java 폴백. python 기본이 아니다.)

### 2. Linux는 mdbtools, 한글은 cp949

```bash
mdb-tables  claim_ledger.mdb
mdb-schema  claim_ledger.mdb
mdb-export -Q -D '%Y-%m-%d' claim_ledger.mdb 클레임원장 \
  | iconv -f cp949 -t utf-8
# 또는
mdb-json claim_ledger.mdb 클레임원장
```

- 한국 97–2003 원장은 텍스트 컬럼이 cp949인 경우가 많다. utf-8로만 읽으면 품번·고장모드가 모지바케다
- `mdb-export` / `mdb-json`은 테이블 단위다. 파일 전체를 메모리에 올리지 않는다
- `polars_access_mdbtools`는 mdbtools를 감싼다. 표가 바로 Polars면 1층에 쓰기 쉽다
- Windows에 Access가 있으면 ACE ODBC도 보조다. VBA는 실행하지 않는다
- python `access_parser`는 ACE 위주이고 파일 전체를 로드한다. Jet 기본 경로가 아니다. 대용량 금지

날짜·Memo(원인/대책) 손실은 표본 20개로 본다. 변환 성공이 품질 성공이 아니다.

### 3. 이후는 31과 완전히 같다

내보낸 표는 가족 C다. Docling을 타지 않는다. Docling은 visio/cad/access를 파싱하지 않는다.

- 1층 Parquet, 원본 컬럼 유지, `source_file` + `table_name`
- 관계는 스키마 카탈로그. Codex `describe_table`이 FK를 본다
- 파일당 테이블 금지. 클레임 원장이면 공통 팩트 2층
- 쿼리 결과를 원장과 UNION하지 않는다
- 원인/대책 긴 칸은 RAG 복제, 테이블에서 삭제하지 않는다

### 4. 잠금

공유 폴더에서 Access 97–2003가 `.ldb`를 남긴다. 열린 파일을 읽으면 부분 dump가 나온다. 복사 후 복사본을 export 한다. 원본 `.mdb`는 삭제하지 않는다.

## 흔한 실패

- `.mdb`를 extract-msg에 넣어 메일 아닌 OLE 잔해 임베딩
- utf-8로 export 해 한글 컬럼이 `????`
- Jet를 access_parser만으로 열어 빈 테이블 또는 OOM
- `.ldb` 잠금을 무시하고 0건 dump
- MSys*까지 적재
- 변환 후 31이 아니라 텍스트 청크로 우회
- Docling이 Access를 받는다고 입고 로그에 원본만 남기기

## 하지 말 것

- mdb 원문을 Milvus에 1청크
- strings/cat으로 바이너리를 본문처럼 자르기
- VBA·매크로 실행
- access_parser로 대용량을 한 번에 로드
- 웹 변환 API에 사내 원장 업로드
- 원본 `.mdb` 삭제
- 파일당 SQL 테이블
- `SELECT *`를 Codex에 열어 두기

`.mdb`는 포맷 문제가 아니라 **Jet 게이트 + 인코딩**이다. 테이블만 나오면 이후는 31과 같다.

## 인접 포맷

- `.accdb` → [31-accdb.md](31-accdb.md). 이 문서의 도착점
- Outlook `.msg` → [11-msg.md](11-msg.md). 같은 OLE, 가족 G
- `.xls` → [05-xls.md](05-xls.md). 같은 OLE, 가족 C 스프레드시트
- `.csv` 덤프가 이미 있으면 [06-csv.md](06-csv.md). mdbtools 불필요
- `.xlsx` 원장 → [04-xlsx.md](04-xlsx.md)
