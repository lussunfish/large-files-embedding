# 01 APUE ingest — mixed_table_prose

| 항목 | 값 |
|------|-----|
| 파일 | `sample-input/pdf/01-Advanced Programming in the UNIX Environment- 3rd Edition.pdf` |
| 크기 | 10MB, 1034페이지, 디지털 텍스트층 |
| 일시 | 2026-09-07 |
| 상태 | **solved** — `chunks=607` |

## 증상

```text
uv run python -m large_files_embedding ingest "sample-input/pdf/01-Advanced Programming in the UNIX Environment- 3rd Edition.pdf"
→ family=B format=pdf normalize=false
→ (Docling MatchingPostProcessor WARNING)
→ FAIL reason=mixed_table_prose
```

로그: `debug/ingest-01.log`. 변환은 ~70초 후 검증에서 문서 전체가 거절됨.

## 원인

607 청크 중 TEXT 496 / table 111. 느슨한 휴리스틱(`|` AND `---` AND `. `)에 걸린 TEXT는 **3개**, 모두 오탐:

- p.141, p.172, p.669: C 예제·`ls -l`·셸 파이프와 본문 문장
- 마크다운 표 구분행(`| --- | --- |`)은 **0건**

UC-03이 거부하려는 것은 “표를 본문 문장에 섞은 청크”이지, 코드 블록의 `|`/`---`가 아니다.

## 해결

`_mixed_table_prose`는 마크다운 표 구분행(`| --- | --- |`)이 있고 문장이 있을 때만 true. 코드/`ls`/`---` ASCII는 통과.

테스트: `test_tables_mixed_into_prose_are_rejected` 유지, `test_code_listing_with_pipes_and_dashes_is_not_mixed_table_prose` 추가.

## 검증

```text
sample-input/pdf/01-Advanced Programming in the UNIX Environment- 3rd Edition.pdf chunks=607 collection=market_quality_chunks_hybrid json=6706d1ca582d70ac/docling.json
```

로그: `debug/ingest-01-retry.log`
