"""UC-01: route files by content signature to family A/B/C/D."""

from pathlib import Path

from large_files_embedding.application.route_file import RouteFile
from large_files_embedding.domain.document import (
    DocumentFamily,
    DocumentFormat,
    FailureReason,
    FileSignature,
    SignatureKind,
)


class FakeFormatDetector:
    def __init__(self, signatures: dict[Path, FileSignature]) -> None:
        self._signatures = signatures

    def detect(self, path: Path) -> FileSignature:
        return self._signatures[path]


def _route(path: Path, signature: FileSignature) -> RouteFile:
    return RouteFile(FakeFormatDetector({path: signature}))


def test_ooxml_with_doc_extension_routes_to_family_a() -> None:
    path = Path("claim_8d.doc")
    router = _route(path, FileSignature(SignatureKind.OOXML_WORD))

    document = router.execute(path)

    assert document.decision is not None
    assert document.decision.family is DocumentFamily.A
    assert document.decision.detected_format is DocumentFormat.DOCX
    assert document.decision.needs_normalization is False
    assert router.failure_queue == []


def test_rtf_disguised_as_doc_goes_to_failure_queue() -> None:
    path = Path("claim_8d.doc")
    router = _route(path, FileSignature(SignatureKind.RTF))

    document = router.execute(path)

    assert document.decision is None
    assert document.queued_for_failure is True
    assert document.failure_reason is FailureReason.RTF
    assert router.failure_queue == [document]


def test_ole_doc_is_family_a_and_needs_soffice() -> None:
    path = Path("legacy.doc")
    router = _route(path, FileSignature(SignatureKind.OLE_WORD))

    document = router.execute(path)

    assert document.decision is not None
    assert document.decision.family is DocumentFamily.A
    assert document.decision.detected_format is DocumentFormat.DOC
    assert document.decision.needs_normalization is True


def test_pdf_routes_to_family_b() -> None:
    path = Path("scan.pdf")
    router = _route(path, FileSignature(SignatureKind.PDF))

    document = router.execute(path)

    assert document.decision is not None
    assert document.decision.family is DocumentFamily.B
    assert document.decision.detected_format is DocumentFormat.PDF
    assert document.decision.needs_normalization is False


def test_ole_xls_is_family_c_with_calamine_not_soffice() -> None:
    path = Path("ledger.xls")
    router = _route(path, FileSignature(SignatureKind.OLE_SHEET))

    document = router.execute(path)

    assert document.decision is not None
    assert document.decision.family is DocumentFamily.C
    assert document.decision.detected_format is DocumentFormat.XLS
    assert document.decision.needs_normalization is False
    assert document.decision.preferred_engine == "calamine"


def test_zip_with_xls_extension_reclassified_as_xlsx_family_c() -> None:
    path = Path("ledger.xls")
    router = _route(path, FileSignature(SignatureKind.OOXML_SHEET))

    document = router.execute(path)

    assert document.decision is not None
    assert document.decision.family is DocumentFamily.C
    assert document.decision.detected_format is DocumentFormat.XLSX
    assert document.decision.needs_normalization is False


def test_ooxml_with_ppt_extension_routes_to_family_d() -> None:
    path = Path("review.ppt")
    router = _route(path, FileSignature(SignatureKind.OOXML_SLIDE))

    document = router.execute(path)

    assert document.decision is not None
    assert document.decision.family is DocumentFamily.D
    assert document.decision.detected_format is DocumentFormat.PPTX
    assert document.decision.needs_normalization is False


def test_ole_ppt_is_family_d_and_needs_soffice() -> None:
    path = Path("review.ppt")
    router = _route(path, FileSignature(SignatureKind.OLE_SLIDE))

    document = router.execute(path)

    assert document.decision is not None
    assert document.decision.family is DocumentFamily.D
    assert document.decision.detected_format is DocumentFormat.PPT
    assert document.decision.needs_normalization is True


def test_tabular_csv_routes_to_family_c() -> None:
    path = Path("claims.csv")
    router = _route(path, FileSignature(SignatureKind.CSV, csv_column_count=3))

    document = router.execute(path)

    assert document.decision is not None
    assert document.decision.family is DocumentFamily.C
    assert document.decision.detected_format is DocumentFormat.CSV


def test_one_column_prose_csv_goes_to_failure_queue() -> None:
    path = Path("memo.csv")
    router = _route(path, FileSignature(SignatureKind.CSV, csv_column_count=1))

    document = router.execute(path)

    assert document.queued_for_failure is True
    assert document.failure_reason is FailureReason.CSV_PROSE
    assert router.failure_queue == [document]


def test_unknown_signature_goes_to_failure_queue_and_does_not_stop_batch() -> None:
    good = Path("ok.pdf")
    bad = Path("mystery.bin")
    hwp = Path("letter.hwp")
    detector = FakeFormatDetector(
        {
            good: FileSignature(SignatureKind.PDF),
            bad: FileSignature(SignatureKind.UNKNOWN),
            hwp: FileSignature(SignatureKind.UNSUPPORTED),
        }
    )
    router = RouteFile(detector)

    outcomes = router.execute_many([bad, hwp, good])

    assert outcomes[0].queued_for_failure is True
    assert outcomes[0].failure_reason is FailureReason.UNKNOWN_SIGNATURE
    assert outcomes[1].queued_for_failure is True
    assert outcomes[1].failure_reason is FailureReason.OUT_OF_SCOPE
    assert outcomes[2].decision is not None
    assert outcomes[2].decision.family is DocumentFamily.B
    assert [item.path for item in router.failure_queue] == [bad, hwp]
