"""UC-04 integration: skip if 01-stable MariaDB/MinIO are down."""

from __future__ import annotations

import inspect
import io
import json
import os
import socket
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile

import polars as pl
import pytest
from typer.testing import CliRunner

from large_files_embedding.application.ingest_tabular import IngestTabular
from large_files_embedding.domain.document import (
    MARKET_QUALITY_BUCKET,
    Document,
    FileSignature,
    SignatureKind,
)
from large_files_embedding.infrastructure.calamine_extractor import (
    CalamineTabularExtractor,
)
from large_files_embedding.infrastructure.mariadb_table_store import MariaDbTableStore
from large_files_embedding.infrastructure.minio_object_store import MinioObjectStore
from large_files_embedding.presentation.cli.main import app

_PKG = "http://schemas.openxmlformats.org/package/2006"
_OD = "http://schemas.openxmlformats.org/officeDocument/2006"
_SS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_REL = "http://schemas.openxmlformats.org/package/2006/relationships"


def _http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            return 200 <= response.status < 500
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _port_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1):
            return True
    except OSError:
        return False


def _infra_skip_reason() -> str | None:
    missing: list[str] = []
    if not _http_ok("http://127.0.0.1:9000/minio/health/live"):
        missing.append("minio")
    if not _port_open("127.0.0.1", 3306):
        missing.append("mariadb")
    if missing:
        return "01-stable down: " + ", ".join(missing)
    return None


def _require_infra() -> None:
    reason = _infra_skip_reason()
    if reason is not None:
        pytest.skip(reason)
    try:
        MariaDbTableStore.from_env().ensure_schema()
    except Exception as exc:
        pytest.skip(f"mariadb: {exc}")


def _minio_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "MINIO_ACCESS_KEY",
        os.environ.get("MINIO_ACCESS_KEY") or "minioadmin",
    )
    monkeypatch.setenv(
        "MINIO_SECRET_KEY",
        os.environ.get("MINIO_SECRET_KEY") or "minioadmin",
    )
    monkeypatch.setenv("MINIO_BUCKET", MARKET_QUALITY_BUCKET)
    monkeypatch.setenv("MINIO_ENDPOINT", "http://127.0.0.1:9000")
    monkeypatch.setenv("MARIADB_HOST", os.environ.get("MARIADB_HOST", "127.0.0.1"))
    monkeypatch.setenv("MARIADB_PORT", os.environ.get("MARIADB_PORT", "3306"))
    monkeypatch.setenv(
        "MARIADB_DATABASE", os.environ.get("MARIADB_DATABASE", "market_quality")
    )
    if os.environ.get("MARIADB_USER"):
        monkeypatch.setenv("MARIADB_USER", os.environ["MARIADB_USER"])
    if os.environ.get("MARIADB_PASSWORD"):
        monkeypatch.setenv("MARIADB_PASSWORD", os.environ["MARIADB_PASSWORD"])


def _col_letter(index: int) -> str:
    result = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _cell_xml(ref: str, value: object) -> str:
    if isinstance(value, bool) or not isinstance(value, int | float):
        text = escape(str(value))
        return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'
    return f'<c r="{ref}"><v>{value}</v></c>'


def _write_xlsx(path: Path, sheets: dict[str, list[list[object]]]) -> Path:
    sheet_items = list(sheets.items())
    rels_ct = "application/vnd.openxmlformats-package.relationships+xml"
    xlsx_main = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
    )
    sheet_ct = (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"
    )
    content_types = [
        f'<Default Extension="rels" ContentType="{rels_ct}"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        f'<Override PartName="/xl/workbook.xml" ContentType="{xlsx_main}"/>',
    ]
    for index, _name in enumerate(sheet_items, start=1):
        content_types.append(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
            f'ContentType="{sheet_ct}"/>'
        )
    workbook_sheets = []
    workbook_rels = []
    for index, (name, _rows) in enumerate(sheet_items, start=1):
        workbook_sheets.append(
            f'<sheet name="{escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
        )
        workbook_rels.append(
            f'<Relationship Id="rId{index}" '
            f'Type="{_OD}/relationships/worksheet" '
            f'Target="worksheets/sheet{index}.xml"/>'
        )
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Types xmlns="{_PKG}/content-types">'
            + "".join(content_types)
            + "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{_REL}">'
            '<Relationship Id="rId1" '
            f'Type="{_OD}/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "xl/workbook.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<workbook xmlns="{_SS}" xmlns:r="{_OD}/relationships">'
            f"<sheets>{''.join(workbook_sheets)}</sheets>"
            "</workbook>",
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{_REL}">'
            + "".join(workbook_rels)
            + "</Relationships>",
        )
        for index, (_name, rows) in enumerate(sheet_items, start=1):
            row_xml = []
            for r_index, row in enumerate(rows, start=1):
                cells = "".join(
                    _cell_xml(f"{_col_letter(c_index)}{r_index}", value)
                    for c_index, value in enumerate(row)
                )
                row_xml.append(f'<row r="{r_index}">{cells}</row>')
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<worksheet xmlns="{_SS}"><sheetData>'
                + "".join(row_xml)
                + "</sheetData></worksheet>",
            )
    return path


def test_extractor_and_store_avoid_forbidden_engines() -> None:
    extractor_module = inspect.getmodule(CalamineTabularExtractor)
    store_module = inspect.getmodule(MariaDbTableStore)
    assert extractor_module is not None
    assert store_module is not None
    extractor_src = inspect.getsource(extractor_module)
    store_src = inspect.getsource(store_module)
    for forbidden in (
        "import pandas",
        "from pandas",
        "import xlrd",
        "from xlrd",
        "import openpyxl",
        "from openpyxl",
        "import docling",
        "from docling",
        "win32com",
        "xlwings",
    ):
        assert forbidden not in extractor_src
    assert "fastexcel" in extractor_src or "calamine" in extractor_src
    assert "scan_csv" in extractor_src
    assert "sink_parquet" in extractor_src
    assert "header_row=None" in extractor_src
    assert "body.iter_rows" not in extractor_src
    assert "_map_facts_from_parquet" not in extractor_src
    assert "VECTOR" not in store_src
    assert "LONGBLOB" not in store_src
    assert "embeddings.chunks" not in store_src
    assert "GRANT ALL" not in store_src
    assert "MARIADB_ROOT_PASSWORD" not in store_src
    assert "DEFAULT_MARIADB_DATABASE" in store_src
    assert "claim_event" in store_src
    assert "monthly_quality_kpi" in store_src
    assert "cause" in store_src
    assert "countermeasure" in store_src


def test_csv_and_xlsx_ingest_to_minio_and_mariadb(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _minio_creds(monkeypatch)
    _require_infra()
    csv_path = tmp_path / "claim_2024-01.csv"
    csv_path.write_text(
        "품번,차종,발생일,원인,대책,건수\nA-1,SUV,2024-01-15,누유,가스켓 교체,3\n",
        encoding="utf-8-sig",
    )
    xlsx_path = tmp_path / "ledger.xlsx"
    _write_xlsx(
        xlsx_path,
        {
            "원장": [
                ["품번", "차종", "발생일", "원인", "대책", "건수"],
                ["B-2", "SEDAN", 44927, "소음", "체결 재작업", 1],
            ],
            "차트1": [["x"], [1]],
        },
    )
    objects = MinioObjectStore.from_env()
    tables = MariaDbTableStore.from_env()
    uc = IngestTabular(CalamineTabularExtractor(), tables, objects)
    csv_result = uc.execute(
        Document.from_signature(csv_path, FileSignature(SignatureKind.CSV, 6))
    )
    xlsx_result = uc.execute(
        Document.from_signature(xlsx_path, FileSignature(SignatureKind.OOXML_SHEET))
    )
    assert csv_result.failed is False
    assert xlsx_result.failed is False
    assert csv_result.fact_table == "claim_event"
    assert xlsx_result.fact_table == "claim_event"
    assert csv_result.profile_key
    profile = json.loads(_minio_get(objects, csv_result.profile_key))
    assert "header_candidates" in profile["sheets"][0]
    assert len(profile["sheets"][0]["sample_rows"]) <= 5
    assert xlsx_result.parquet_keys
    assert all("차트1" not in key for key in xlsx_result.parquet_keys)
    rows = _claim_rows(tables, csv_path.name)
    assert rows
    csv_causes = _claim_causes(tables, csv_path.name)
    assert "누유" in csv_causes
    assert "가스켓 교체" in _claim_counters(tables, csv_path.name)
    parquet = pl.read_parquet(
        io.BytesIO(_minio_get(objects, xlsx_result.parquet_keys[0]))
    )
    assert "원인" in parquet.columns
    assert "대책" in parquet.columns
    assert "source_file" in parquet.columns
    assert "sheet_name" in parquet.columns
    dates = [str(value) for value in parquet["발생일"].to_list()]
    assert any("2023-01-01" in value for value in dates)
    assert "2023-01-01" in _claim_event_dates(tables, xlsx_path.name)


def test_snapshot_without_period_stays_layer1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _minio_creds(monkeypatch)
    _require_infra()
    path = tmp_path / "monthly.xlsx"
    _write_xlsx(
        path,
        {
            "월보": [
                ["차종", "클레임건수", "PPM"],
                ["SUV", 12, 3.5],
            ]
        },
    )
    objects = MinioObjectStore.from_env()
    tables = MariaDbTableStore.from_env()
    result = IngestTabular(CalamineTabularExtractor(), tables, objects).execute(
        Document.from_signature(path, FileSignature(SignatureKind.OOXML_SHEET))
    )
    assert result.failed is False
    assert result.fact_table is None
    assert result.parquet_keys
    assert _kpi_count(tables, path.name) == 0


def test_mixed_ledger_and_kpi_sheets_go_to_separate_tables(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _minio_creds(monkeypatch)
    _require_infra()
    path = tmp_path / f"mixed-{uuid.uuid4().hex}-2024-03.xlsx"
    _write_xlsx(
        path,
        {
            "원장": [
                ["품번", "차종", "발생일", "원인", "대책", "건수"],
                ["B-2", "SEDAN", 44927, "소음", "체결 재작업", 1],
            ],
            "월보": [
                ["차종", "클레임건수", "PPM"],
                ["SUV", 12, 3.5],
            ],
        },
    )
    objects = MinioObjectStore.from_env()
    tables = MariaDbTableStore.from_env()
    result = IngestTabular(CalamineTabularExtractor(), tables, objects).execute(
        Document.from_signature(path, FileSignature(SignatureKind.OOXML_SHEET))
    )
    assert result.failed is False
    assert result.fact_table is not None
    assert "claim_event" in result.fact_table
    assert "monthly_quality_kpi" in result.fact_table
    assert _claim_causes(tables, path.name)
    assert _kpi_count(tables, path.name) == 1
    assert len(result.parquet_keys) == 2


def test_title_row_above_header_keeps_layer1_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _minio_creds(monkeypatch)
    _require_infra()
    path = tmp_path / "titled.xlsx"
    _write_xlsx(
        path,
        {
            "원장": [
                ["2024년 1월 시장품질 보고서"],
                ["품번", "차종", "발생일", "원인", "대책", "건수"],
                ["C-9", "SUV", 44927, "누유", "가스켓 교체", 2],
            ]
        },
    )
    objects = MinioObjectStore.from_env()
    tables = MariaDbTableStore.from_env()
    result = IngestTabular(CalamineTabularExtractor(), tables, objects).execute(
        Document.from_signature(path, FileSignature(SignatureKind.OOXML_SHEET))
    )
    assert result.failed is False
    parquet = pl.read_parquet(io.BytesIO(_minio_get(objects, result.parquet_keys[0])))
    assert "원인" in parquet.columns
    assert "대책" in parquet.columns
    assert "품번" in parquet.columns
    assert result.fact_table == "claim_event"
    assert "누유" in _claim_causes(tables, path.name)


def test_cli_ingests_family_c_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _minio_creds(monkeypatch)
    _require_infra()
    path = tmp_path / "claim_2024-02.csv"
    path.write_text(
        "품번,차종,발생일,원인,대책,건수\nC-3,SUV,2024-02-01,누유,교체,2\n",
        encoding="utf-8",
    )
    result = CliRunner().invoke(app, ["ingest", str(path)])
    assert result.exit_code == 0
    assert "family=C" in result.stdout
    assert "skip=tabular" not in result.stdout
    assert "fact=claim_event" in result.stdout
    assert "chunks=" not in result.stdout


def _minio_get(store: MinioObjectStore, key: str) -> bytes:
    client = store._client_or_connect()
    response = client.get_object(store._bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def _claim_causes(store: MariaDbTableStore, source_file: str) -> list[str]:
    connection = store._connect()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT cause FROM claim_event WHERE source_file=%s",
            (source_file,),
        )
        return [str(row[0]) for row in cursor.fetchall() if row[0] is not None]


def _claim_counters(store: MariaDbTableStore, source_file: str) -> list[str]:
    connection = store._connect()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT countermeasure FROM claim_event WHERE source_file=%s",
            (source_file,),
        )
        return [str(row[0]) for row in cursor.fetchall() if row[0] is not None]


def _claim_rows(store: MariaDbTableStore, source_file: str) -> list[tuple[object, ...]]:
    connection = store._connect()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT cause, countermeasure FROM claim_event WHERE source_file=%s",
            (source_file,),
        )
        return list(cursor.fetchall())


def _claim_event_dates(store: MariaDbTableStore, source_file: str) -> list[str]:
    connection = store._connect()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT event_date FROM claim_event WHERE source_file=%s",
            (source_file,),
        )
        return [str(row[0]) for row in cursor.fetchall() if row[0] is not None]


def _kpi_count(store: MariaDbTableStore, source_file: str) -> int:
    connection = store._connect()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT COUNT(*) FROM monthly_quality_kpi WHERE source_file=%s",
            (source_file,),
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0
