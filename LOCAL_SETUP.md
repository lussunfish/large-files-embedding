# 로컬 설치 항목 (구현 전)

대상: `PLAN.md` UC-01~06, 포맷 01–08. 호스트는 macOS, 실행 모드 `uv-native`.

Python 라이브러리는 프로젝트 `.venv`에 넣는다. 시스템 Python(3.9)에는 설치하지 않는다.

## 상태 (2026-09-05 설치 후)

| 항목 | 필요 여부 | 이 머신 |
|------|-----------|---------|
| Homebrew | OS 패키지 | 있음 (6.0.21) |
| Git | 저장소 | 있음 (2.50.1) |
| uv | 패키지·venv | 있음 (0.11.25) |
| Python 3.12 | 런타임 | 있음 (`python3.12` 3.12.14). `/usr/bin/python3`는 3.9라 쓰지 않음 |
| LibreOffice (`soffice`) | UC-02 `.doc`/`.ppt` | **설치됨** 26.8.0.3 (`/opt/homebrew/bin/soffice`) |
| Noto Sans CJK KR | soffice 한글 | **설치됨** `~/Library/Fonts/NotoSansCJKkr-*.otf` |
| libmagic | 시그니처(python-magic) | **설치됨** 5.48 |
| 프로젝트 `.venv` | Python 라이브러리 | **설치됨** (docling 2.126, polars, duckdb, pymilvus, mcp, sentence-transformers, …) |
| 공유 인프라 (OrbStack) | MariaDB·Milvus·MinIO | **실행 중** (`01-stable`). 이 레포에서 compose 하지 않음. 상세는 PLAN 인프라 절 |
| Ollama | UC-03/05 dense 임베딩 | **실행 중** `127.0.0.1:11434`. 모델 `qwen3-embedding:4b` (2.5GB) **pull 됨** |
| GPU / CUDA | PLAN `USE_GPU=no` | 설치하지 않음. Ollama가 호스트에서 임베딩 추론 |

## A. OS 패키지 (지금 설치)

```bash
brew install libmagic
brew install --cask font-noto-sans-cjk-kr
brew install --cask libreoffice
```

설치 후:

```bash
# soffice PATH (앱 번들)
export PATH="/Applications/LibreOffice.app/Contents/MacOS:$PATH"
soffice --version

# 선택: 셸 설정에 추가하거나 DOCLING_LIBREOFFICE_CMD 지정
export DOCLING_LIBREOFFICE_CMD="/Applications/LibreOffice.app/Contents/MacOS/soffice"
```

`python-magic`은 Homebrew `libmagic`이 있어야 한다. 대안은 `filetype`(순수 Python)이며 PLAN 라우터는 둘 중 하나면 된다.

## B. Python 3.12 venv + 라이브러리 (지금 설치)

`/scaffold` 이전이라도 가중치·휠을 받아 두기 위해 프로젝트 `.venv`를 만든다. 이후 `pyproject.toml`이 생기면 같은 3.12로 `uv sync`한다.

```bash
uv venv --python 3.12 .venv
source .venv/bin/activate   # 또는 uv pip --python .venv

uv pip install --python .venv \
  "docling[rapidocr]" \
  polars fastexcel python-calamine \
  duckdb pyarrow \
  pymilvus \
  mcp typer \
  python-magic charset-normalizer filetype \
  "sentence-transformers" \
  pytest ruff mypy
```

| 패키지 | UC |
|--------|-----|
| `docling[rapidocr]` | UC-03 PDF/DOCX/PPTX, 한글 OCR |
| `polars` `fastexcel` `python-calamine` | UC-04 표 추출 |
| `duckdb` `pyarrow` | UC-04 Parquet·조회 |
| `pymilvus` | UC-03/05 Milvus Lite |
| `mcp` `typer` | UC-05/06 서버·CLI |
| `python-magic` `filetype` `charset-normalizer` | UC-01 시그니처, UC-04 인코딩 |
| `sentence-transformers` | 선택. 서술 dense 기본은 Ollama `qwen3-embedding:4b` |
| `pytest` `ruff` `mypy` | TDD·커밋 전 검사 |

Docling RapidOCR·레이아웃 가중치는 **첫 변환 시** Hugging Face에서 내려받는다. 오프라인 CI는 캐시를 미리 채워야 한다.

## C. Ollama 임베딩 (호스트, 이미 있음)

서술 청크 dense는 **Ollama** `qwen3-embedding:4b`다. 벡터 저장소는 Milvus다. MariaDB `embeddings.chunks` VECTOR에 넣지 않는다.

```bash
# 없으면 설치·pull. 이 머신은 2026-09-05 기준 이미 있음
ollama --version
ollama pull qwen3-embedding:4b
curl -fsS http://127.0.0.1:11434/api/tags
```

헬스(모델 이름 확인):

```bash
curl -fsS http://127.0.0.1:11434/api/embed \
  -d '{"model":"qwen3-embedding:4b","input":"ok"}'
```

기본 출력 dim은 **2560**. Milvus 컬렉션 스키마와 맞출 것.

## D. 설치하지 않는 것 (비목표·후속)

- Docker, Milvus standalone, MariaDB (공유 `01-stable` 사용)
- ColQwen / ColPali / GPU 드라이버
- 한컴 오피스 (09 HWP)
- JODConverter (대량 soffice 풀, 후속)
- 서술 dense를 sentence-transformers BGE-M3로 기본 경로 삼기 (Ollama `qwen3-embedding:4b`가 기본)

## E. 설치 후 확인

```bash
uv run --python .venv python -c "import sys; print(sys.version)"
uv run --python .venv python -c "import docling, polars, duckdb, pymilvus, mcp; print('pyok')"
/Applications/LibreOffice.app/Contents/MacOS/soffice --version
ls ~/Library/Fonts | grep -i noto || true
curl -fsS http://127.0.0.1:11434/api/tags | grep qwen3-embedding
```

## F. 구현 순서와의 관계

1. 이 파일의 A·B·C 설치
2. `PLAN.md` `approved`
3. `/scaffold` (`pyproject.toml`, `scripts/stop.sh`)
4. `/implement-uc UC-01`
