# RTF 권장 파이프라인

- 배경: 시장품질 RAG/MCP에서 RTF(가족 A)를 어떻게 넣을 것인가. 서술 문서이지 표 저장소가 아니다.
- 관련 문서: `../market-quality-rag-improvement.md`, `README.md`

## 결론

RTF는 본문·제목·표가 있는 서술 문서다. CSV/엑셀처럼 Parquet에 넣지 않는다. Docling 공식 입력 목록에 RTF는 없다. 네이티브 백엔드가 아니다. **LibreOffice로 `.docx`로 바꾼 뒤 `02-docx.md`와 동일**하다. `catdoc`/`unrtf`는 표와 한글이 깨지므로 기본 경로가 아니다.

권장 한 줄:

```
.rtf (원본 보관) → 시그니처({\rtf) → LibreOffice headless → .docx
                 → SimplePipeline JSON + HybridChunker → Milvus
                 → MCP: outline / section / table
```

| 선택 | 판단 |
|---|---|
| `unrtf` / `catdoc`으로 텍스트 dump | 하지 말 것 (표·한글 깨짐) |
| RTF를 평문처럼 512토큰 자르기 | 하지 말 것 |
| Docling에 `.rtf`를 바로 넣기 | 하지 말 것. 공식 입력이 아님 |
| LibreOffice → `.docx` 후 02 파이프라인 | **기본 경로** |
| RTF를 CSV/표 저장소로 취급 | 하지 말 것 |
| PDF로 먼저 변환 | 기본 경로 아님 |
| 변환본만 남기고 원본 삭제 | 하지 말 것 |

확장자가 `.doc`인데 실제로는 RTF인 파일이 많다. 시그니처를 먼저 본다. `.doc`와 달리 Docling 내장 `convert_to_modern_format` 경로도 없다.

## 권장 파이프라인

```
업로드 .rtf 또는 위장 .doc
  1. 시그니처 확인
       {\rtf 로 시작하면 RTF
       OLE이면 03-doc.md, OOXML이면 02-docx.md
  2. 정규화
       soffice --headless → .docx
       원본 보관, 변환본은 파생물
  3. 이후
       02-docx.md 와 동일
       SimplePipeline JSON → HybridChunker → Milvus
  4. MCP
       get_outline, get_section, get_table, search_passages
```

```bash
soffice --headless --norestore --nolockcheck \
  -env:UserInstallation=file:///tmp/lo_profile_$JOB_ID \
  --convert-to docx:"MS Word 2007 XML" \
  --outdir /data/normalized \
  claim_8d.rtf
```

## 단계별 권장

### 1. 시그니처: `.doc`로 위장된 RTF

매직은 파일 앞의 `{\rtf`다. `file` 결과가 `Rich Text Format`이면 확장자와 무관하게 이 경로다.

```bash
file memo.doc
# Rich Text Format    → 이 문서
# Word 97-2003        → 03-doc.md
# Microsoft Word 2007+ → 02-docx.md
```

위장 `.doc`를 OLE 변환에 넣으면 실패 로그가 섞인다.

### 2. 변환은 LibreOffice, 텍스트 추출기는 보조가 아니다

`unrtf`, `catdoc`, 단순 RTF 스트리퍼는 한글(cp949/유니코드 제어어)과 표를 거의 버린다. 시장품질 8D·대책서에서 제목 계층과 표가 본체인 경우가 많다.

운영 규칙은 `.doc`와 같다.

- 컨테이너에 `fonts-noto-cjk` / `fonts-nanum`
- soffice는 스레드 안전하지 않다. 워커 하나 또는 파일별 `UserInstallation`
- 타임아웃, `failed_rtf` 격리. 기본 프로필 공유 금지 (#3819와 같은 hang·락)
- 메타: `converted_from`, `converter=libreoffice`, `converted_at`

### 3. 변환 후는 02와 동일

Heading, HybridChunker(`repeat_table_header=True`, `chunker.contextualize(chunk)`), 표 CSV 분리, `python-docx` 헤더/푸터 품번은 `02-docx.md`를 따른다. RTF 전용 청커를 만들지 않는다.

RTF 안에 표가 있어도 그것은 문서 안 집계다. 행을 Milvus에 문장으로 넣지 않고, Word 표와 같이 `table` 청크로 둔다. 반복 양식이 수백 건이면 그때 SQL 2층을 검토한다.

### 4. MCP

도구는 Word와 같다. `search` 하나만 두지 않는다. `get_outline`, `get_section`, `get_table`이 담당자 질의에 맞다. 인용은 원본 파일명과 섹션 경로를 쓴다.

## 흔한 실패

- `.doc`로 저장된 RTF를 OLE 게이트에 넣어 실패한다
- `unrtf`로 뽑아 표가 사라지고 한글이 깨진다
- CJK 폰트 없이 변환해 `□□`가 된다
- soffice 병렬 실행으로 프로세스가 죽는다
- RTF를 txt로 보고 문단 분할만 한다
- 변환 실패 파일을 빈 문서로 인덱싱한다

## 하지 말 것

- `catdoc` / `unrtf`를 기본 추출기로 쓰는 것
- RTF를 CSV·로그로 재분류하지 않은 채 가족 C에 넣는 것
- 마크다운 dump + 토큰 청크를 기본으로 쓰는 것
- Docling에 `.rtf`를 네이티브 입력으로 넣는 것
- 웹 변환 API에 사내 문서를 올리는 것
- 원본을 지우고 변환본만 남기는 것
- PDF로 바꿔 가족 B에 넣는 것

## 인접 포맷

- 변환 후 파싱은 `02-docx.md`
- 진짜 `.doc`(OLE)는 `03-doc.md`
- 평문 `.txt`는 가족 E. RTF를 txt로 취급하지 않는다. `15-txt.md`
- 정형 표는 xlsx/csv. RTF가 아니다. `04-xlsx.md`, `06-csv.md`
