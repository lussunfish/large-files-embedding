"""UC-01 integration: MagicFormatDetector + RouteFile on real bytes."""

import zipfile
from pathlib import Path

from typer.testing import CliRunner

from large_files_embedding.application.route_file import RouteFile
from large_files_embedding.domain.document import (
    DocumentFamily,
    DocumentFormat,
    FailureReason,
)
from large_files_embedding.infrastructure.format_detector import MagicFormatDetector
from large_files_embedding.presentation.cli.main import app

OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")


def _ooxml(path: Path, part: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types></Types>')
        archive.writestr(f"{part}/document.xml", "<x/>")


def _ole(path: Path, *streams: str) -> None:
    payload = bytearray(OLE_MAGIC + b"\x00" * 256)
    for stream in streams:
        payload.extend(stream.encode("utf-16le"))
    path.write_bytes(payload)


def _router() -> RouteFile:
    return RouteFile(MagicFormatDetector())


def test_ooxml_named_doc_is_family_a(tmp_path: Path) -> None:
    path = tmp_path / "claim.doc"
    _ooxml(path, "word")
    document = _router().execute(path)
    assert document.decision is not None
    assert document.decision.family is DocumentFamily.A
    assert document.decision.detected_format is DocumentFormat.DOCX
    assert document.decision.needs_normalization is False


def test_rtf_named_doc_is_failure_queue(tmp_path: Path) -> None:
    path = tmp_path / "claim.doc"
    path.write_bytes(b"{\\rtf1\\ansi disguised}")
    document = _router().execute(path)
    assert document.queued_for_failure is True
    assert document.failure_reason is FailureReason.RTF


def test_pdf_is_family_b(tmp_path: Path) -> None:
    path = tmp_path / "a.pdf"
    path.write_bytes(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n")
    document = _router().execute(path)
    assert document.decision is not None
    assert document.decision.family is DocumentFamily.B
    assert document.decision.detected_format is DocumentFormat.PDF


def test_zip_named_xls_is_xlsx_family_c(tmp_path: Path) -> None:
    path = tmp_path / "ledger.xls"
    _ooxml(path, "xl")
    document = _router().execute(path)
    assert document.decision is not None
    assert document.decision.family is DocumentFamily.C
    assert document.decision.detected_format is DocumentFormat.XLSX


def test_ooxml_named_ppt_is_family_d(tmp_path: Path) -> None:
    path = tmp_path / "review.ppt"
    _ooxml(path, "ppt")
    document = _router().execute(path)
    assert document.decision is not None
    assert document.decision.family is DocumentFamily.D
    assert document.decision.detected_format is DocumentFormat.PPTX
    assert document.decision.needs_normalization is False


def test_ole_xls_prefers_calamine(tmp_path: Path) -> None:
    path = tmp_path / "ledger.xls"
    _ole(path, "Workbook")
    document = _router().execute(path)
    assert document.decision is not None
    assert document.decision.family is DocumentFamily.C
    assert document.decision.detected_format is DocumentFormat.XLS
    assert document.decision.needs_normalization is False
    assert document.decision.preferred_engine == "calamine"


def test_ole_doc_needs_normalization(tmp_path: Path) -> None:
    path = tmp_path / "legacy.doc"
    _ole(path, "WordDocument")
    document = _router().execute(path)
    assert document.decision is not None
    assert document.decision.family is DocumentFamily.A
    assert document.decision.detected_format is DocumentFormat.DOC
    assert document.decision.needs_normalization is True


def test_ole_ppt_needs_normalization(tmp_path: Path) -> None:
    path = tmp_path / "review.ppt"
    _ole(path, "PowerPoint Document")
    document = _router().execute(path)
    assert document.decision is not None
    assert document.decision.family is DocumentFamily.D
    assert document.decision.detected_format is DocumentFormat.PPT
    assert document.decision.needs_normalization is True


def test_ole_ppt_with_embedded_workbook_is_family_d_not_xls(tmp_path: Path) -> None:
    path = tmp_path / "review.ppt"
    _ole(path, "Workbook", "PowerPoint Document")
    document = _router().execute(path)
    assert document.decision is not None
    assert document.decision.family is DocumentFamily.D
    assert document.decision.detected_format is DocumentFormat.PPT
    assert document.decision.needs_normalization is True
    assert document.decision.preferred_engine is None


def test_ole_excel5_book_entry_is_family_c(tmp_path: Path) -> None:
    path = tmp_path / "legacy.xls"
    path.write_bytes(
        OLE_MAGIC + b"\x00" * 256 + "Book".encode("utf-16le") + b"\x00\x00"
    )
    document = _router().execute(path)
    assert document.decision is not None
    assert document.decision.family is DocumentFamily.C
    assert document.decision.detected_format is DocumentFormat.XLS
    assert document.decision.preferred_engine == "calamine"


def test_ole_book_substring_is_not_xls(tmp_path: Path) -> None:
    path = tmp_path / "notes.bin"
    path.write_bytes(
        OLE_MAGIC + b"\x00" * 256 + "The Book of quality".encode("utf-16le")
    )
    document = _router().execute(path)
    assert document.queued_for_failure is True
    assert document.failure_reason is FailureReason.OUT_OF_SCOPE


def test_tabular_csv_is_family_c(tmp_path: Path) -> None:
    path = tmp_path / "claims.csv"
    path.write_text("part_no,qty,date\nA-1,2,2024-01-01\n", encoding="utf-8")
    document = _router().execute(path)
    assert document.decision is not None
    assert document.decision.family is DocumentFamily.C
    assert document.decision.detected_format is DocumentFormat.CSV


def test_json_object_goes_to_failure_queue(tmp_path: Path) -> None:
    path = tmp_path / "rows.json"
    path.write_text('{"a": 1, "b": 2}\n{"a": 3, "b": 4}\n', encoding="utf-8")
    document = _router().execute(path)
    assert document.queued_for_failure is True
    assert document.failure_reason is FailureReason.OUT_OF_SCOPE


def test_one_column_prose_csv_is_csv_prose(tmp_path: Path) -> None:
    path = tmp_path / "memo.csv"
    path.write_text(
        "memo\n"
        "원인 분석 결과가 한 문장으로 이어진다.\n"
        "대책은 공정 조건을 조정하는 것이다.\n",
        encoding="utf-8",
    )
    document = _router().execute(path)
    assert document.queued_for_failure is True
    assert document.failure_reason is FailureReason.CSV_PROSE


def test_unknown_and_hwp_do_not_stop_batch(tmp_path: Path) -> None:
    pdf = tmp_path / "ok.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    mystery = tmp_path / "mystery.bin"
    mystery.write_bytes(b"\x00\x01\x02\x03not-a-document")
    hwp = tmp_path / "letter.hwp"
    hwp.write_bytes(OLE_MAGIC + b"\x00" * 64 + b"HWP Document File")
    router = _router()
    outcomes = router.execute_many([mystery, hwp, pdf])
    assert outcomes[0].queued_for_failure is True
    assert outcomes[0].failure_reason is FailureReason.UNKNOWN_SIGNATURE
    assert outcomes[1].queued_for_failure is True
    assert outcomes[1].failure_reason is FailureReason.OUT_OF_SCOPE
    assert outcomes[2].decision is not None
    assert outcomes[2].decision.family is DocumentFamily.B


def test_ingest_cli_continues_after_failure(tmp_path: Path) -> None:
    _ooxml(tmp_path / "claim.doc", "word")
    (tmp_path / "fake.doc").write_bytes(b"{\\rtf1\\ansi x}")
    result = CliRunner().invoke(app, ["ingest", str(tmp_path)])
    assert result.exit_code == 0
    assert "family=A" in result.stdout
    assert "FAIL" in result.stdout
    assert "rtf" in result.stdout
