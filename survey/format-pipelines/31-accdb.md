# Access ACCDB 권장 파이프라인

- 배경: 시장품질 클레임 원장이 Access(`.accdb`, ACE 2007+)에 있는 경우가 흔하다. 표는 SQL, 파일 바이너리는 RAG가 아니다. 100MB급도 있다. Docling은 Access를 파싱하지 않는다.
- 관련 문서: `../excel-to-sql-decision.md`, `README.md`

## 결론

`.accdb`는 가족 C다. 파일을 청크하지 않는다. 테이블만 Parquet로 내보내고, 관계는 MCP 카탈로그에 둔다. 폼·리포트·VBA는 버린다. Access가 열어 두면 잠긴다.

| 선택 | 판단 |
|---|---|
| accdb 바이너리를 Milvus에 넣기 | 하지 말 것 |
| 테이블 → Parquet 1층 → SQL 2층 | **기본 경로** |
| 관계(Relationships) → describe_table 카탈로그 | 해야 함 |
| Linux: mdbtools / polars_access_mdbtools | **Linux 기본** |
| Windows: ACE ODBC | **Windows 기본** |
| 암호 ACE: pyaccdb / Jackcess Encrypt | 시크릿으로만. 로그 금지 |
| access_parser로 대용량 로드 | 하지 말 것. 파일 전체를 메모리에 올린다 |
| 쿼리 결과를 기본 적재 | 하지 말 것. 테이블이 본체 |
| 폼·리포트·VBA 인덱싱 | 하지 말 것 |
| 파일마다 SQL 테이블 양산 | 하지 말 것 |
| Access가 연 상태에서 직접 읽기 | 하지 말 것. 잠금 |
| Docling에 accdb 투입 | 하지 말 것. 미지원 |

권장 한 줄:

```
.accdb → 시그니처(ACE) → 잠금이면 복사
      → Linux: mdbtools(mdb-export/mdb-json) 또는 polars_access_mdbtools
      → Windows: ACE ODBC (SELECT만)
      → 암호면 pyaccdb(Agile) / Jackcess. access_parser는 대용량 금지
      → Parquet 1층 → 표준 팩트 SQL 2층
      → 관계는 스키마 카탈로그. 벡터에는 카탈로그만
```

## 권장 파이프라인

```
업로드 .accdb (~100MB 가능)
  1. 시그니처
       ACE/Jet. OLE인데 Outlook이면 11, 엑셀이면 05
       ZIP이면 위조 확장자. 재분류
  2. 잠금
       Access가 열어 두면 .laccdb + exclusive lock
       실패하면 복사본을 읽고 원본은 그대로
  3. 인벤토리
       mdb-tables / mdb-schema
       테이블 / 쿼리 / 리포트 / 폼 / 매크로
       MSys* 시스템 테이블 스킵
  4. 테이블 export
       Linux: mdb-export 또는 mdb-json, 또는 polars_access_mdbtools
       Windows: ACE ODBC SELECT
       암호 ACE: pyaccdb / Jackcess Encrypt
       테이블 단위 → Parquet. 파일 전체 메모리 로드 금지
  5. 관계
       PK/FK, 1:N을 catalog JSON
       MCP describe_table의 Grain·조인 힌트
  6. 1층 Parquet
       source_file, table_name, ingested_at
       원본 컬럼 유지
  7. 2층 SQL
       클레임 원장이면 claims 팩트. 파일당 테이블 금지
  8. MCP (읽기 전용)
       list_tables / describe_table / query_tables
  9. 벡터
       테이블·컬럼·관계 설명만. 행 데이터 금지
```

## 단계별 권장

### 1. 바이너리를 RAG하지 않는다

Access는 컨테이너다. 본문은 테이블 행이다. Docling은 visio/cad/access를 파싱하지 않는다. 텍스트 추출·파일 단위 임베딩은 해당 없다.

- 시그니처가 ACE가 아니면 31을 타지 않는다
- 암호 DB는 시크릿 스토어의 암호로만 연다. 로그·청크·프롬프트에 암호를 넣지 않는다. 암호가 없으면 실패 큐
- 100MB는 테이블 단위 export다. 파일 전체를 메모리에 올리지 않는다

### 2. 추출 도구

Linux 기본은 mdbtools다. VBA를 실행하지 않는 경로만 쓴다.

- **mdbtools**: Linux 표준. `mdb-tables`, `mdb-schema`, `mdb-export`, `mdb-json`. Jet에 강하고 ACE는 제한적(첨부·암호는 자주 실패)
- **polars_access_mdbtools**: mdbtools를 감싼 Polars 리더. 1층 Parquet와 맞다
- **ACE ODBC / ACE OLEDB**: Windows. `SELECT`만, 쓰기·매크로 금지
- **pyaccdb** (2025): ACE `.accdb` python 파서. 페이지 단위. Agile Encryption(암호 accdb) 지원. AGPL
- **Jackcess Encrypt**: 암호 accdb의 Java 경로. python 기본이 아니다
- **access_parser** (`access-parser`): 파일 전체를 메모리에 올린다. 대용량·100MB급 금지. 암호 미지원

쿼리·리포트는 저장 뷰일 뿐이다. 적재 원본은 **물리 테이블**이다. 쿼리 SQL은 카탈로그에 적어 두고, 입고 기본에서 실행하지 않는다.

### 3. 관계 → 스키마 카탈로그

시장품질 Access는 `클레임–품번–고장모드` 1:N이 본체다. 관계창을 버리면 Codex가 조인을 모른다.

- PK/FK, 카디널리티, 테이블 Grain을 `describe_table`에 넣는다
- 폼/리포트 레이아웃은 카탈로그가 아니다
- 파일마다 테이블을 만들지 않는다. 04와 같이 공통 팩트만 2층

### 4. 잠금과 VBA

운영 PC에서 Access가 원장을 연 채로 공유 폴더에 둔다. 읽기 실패는 잠금일 때가 많다.

- `.laccdb`가 있으면 복사 후 복사본을 읽는다
- 폼·매크로·VBA는 파싱도 실행도 하지 않는다
- Attachment 컬럼의 xlsx/pdf는 꺼내 포맷 라우터로 보낸다

### 5. MCP

Codex는 행을 임베딩으로 찾지 않는다.

1. `list_tables(product, period)`
2. `describe_table(name)` — 컬럼, 단위, Grain, FK
3. `query_tables(sql)` — 읽기 전용, LIMIT 강제

벡터는 “`claims` 한 행 = 클레임 1건, `part_no`로 조인” 수준이다. 원인/대책 메모는 RAG 복제, 테이블에서 삭제하지 않는다.

## 흔한 실패

- accdb를 텍스트로 열어 OLE 잔해를 임베딩
- Access가 연 파일을 읽어 0바이트·부분 dump
- MSysObjects까지 적재해 테이블이 수십 개
- 쿼리 결과를 원장과 UNION
- 관계 없이 테이블만 넣어 Codex가 교차 조인
- access_parser로 100MB를 통째로 로드해 OOM
- 원인/대책 Memo를 2층에서 drop
- Docling이 Access를 받는다고 입고 로그에 원본만 남기기

## 하지 말 것

- `.accdb`를 Docling/마크다운으로 우회
- 원문 파일을 Milvus에 1청크
- VBA·매크로 실행
- 파일당 SQL 테이블
- access_parser로 대용량 파일을 한 번에 로드
- 암호를 파이프라인 로그·청크에 남기기
- 웹 변환 API에 사내 원장 업로드
- 원본 accdb 삭제
- `SELECT *`를 Codex에 열어 두기

## 인접 포맷

- `.mdb` → [32-mdb.md](32-mdb.md). Jet. 이후는 이 문서
- `.xlsx`/`.csv` 원장 → [04-xlsx.md](04-xlsx.md), [06-csv.md](06-csv.md). 같은 가족 C
- JSON 레코드 덤프 → [20-json.md](20-json.md)
- Access 안의 첨부 PDF/DOCX → 꺼내서 [01-pdf.md](01-pdf.md) / [02-docx.md](02-docx.md)
- Outlook `.msg` OLE → [11-msg.md](11-msg.md). 메일이면 여기 아님
