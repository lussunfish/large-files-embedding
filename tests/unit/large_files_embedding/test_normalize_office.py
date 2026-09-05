"""UC-02: normalize OLE .doc/.ppt via LibreOffice; original is preserved."""

from datetime import UTC, datetime
from pathlib import Path
from zipfile import ZipFile

import pytest

from large_files_embedding.application.normalize_office import NormalizeOffice
from large_files_embedding.domain.document import (
    ConversionMetadata,
    ConversionTimeout,
    Document,
    DocumentFormat,
    FailureReason,
    FileSignature,
    SignatureKind,
    SofficeMissing,
    UnsupportedConverterError,
    modern_office_target,
    soffice_filter,
)
from large_files_embedding.infrastructure.libreoffice_normalizer import (
    LibreOfficeNormalizer,
)

OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")


class FakeOfficeNormalizer:
    def __init__(
        self,
        *,
        derived: Path | None = None,
        error: Exception | None = None,
        writer: object | None = None,
    ) -> None:
        self.derived = derived
        self.error = error
        self.writer = writer
        self.calls: list[tuple[Path, Path, DocumentFormat, float]] = []

    def convert(
        self,
        source: Path,
        output_dir: Path,
        *,
        source_format: DocumentFormat,
        timeout_seconds: float,
    ) -> Path:
        self.calls.append((source, output_dir, source_format, timeout_seconds))
        if self.error is not None:
            raise self.error
        if self.writer is not None:
            return self.writer(source, output_dir, source_format)
        assert self.derived is not None
        return self.derived


def _document(path: Path, kind: SignatureKind) -> Document:
    return Document.from_signature(path, FileSignature(kind))


def _ole_doc(path: Path) -> Path:
    path.write_bytes(OLE_MAGIC + b"\x00" * 32 + "WordDocument".encode("utf-16le"))
    return path


def _ole_ppt(path: Path) -> Path:
    path.write_bytes(
        OLE_MAGIC + b"\x00" * 32 + "PowerPoint Document".encode("utf-16le")
    )
    return path


def _write_ooxml(path: Path, inner: str, text: str) -> Path:
    with ZipFile(path, "w") as archive:
        archive.writestr(inner, f"<t>{text}</t>")
    return path


def test_timeout_is_treated_as_hang_and_leaves_original(tmp_path: Path) -> None:
    source = _ole_doc(tmp_path / "legacy.doc")
    original = source.read_bytes()
    document = _document(source, SignatureKind.OLE_WORD)
    hanging = FakeOfficeNormalizer(error=ConversionTimeout())

    result = NormalizeOffice(hanging).execute(document)

    assert result.failure_reason is FailureReason.HANG
    assert result.derived_path is None
    assert result.metadata is None
    assert source.exists()
    assert source.read_bytes() == original
    assert hanging.calls
    assert hanging.calls[0][3] > 0


def test_successful_doc_keeps_original_and_writes_docx_metadata(tmp_path: Path) -> None:
    source = _ole_doc(tmp_path / "claim_8d.doc")
    derived = tmp_path / "claim_8d.docx"
    _write_ooxml(derived, "word/document.xml", "원인과 대책")
    document = _document(source, SignatureKind.OLE_WORD)

    result = NormalizeOffice(FakeOfficeNormalizer(derived=derived)).execute(document)

    assert result.failure_reason is None
    assert result.derived_path == derived
    assert source.exists()
    assert derived.exists()
    assert result.metadata is not None
    assert result.metadata.converted_from is DocumentFormat.DOC
    assert result.metadata.converter == "libreoffice"
    assert result.metadata.converted_at.tzinfo is UTC
    assert result.metadata.converted_at <= datetime.now(UTC)


def test_successful_ppt_keeps_original_and_writes_pptx_metadata(tmp_path: Path) -> None:
    source = _ole_ppt(tmp_path / "review.ppt")
    derived = tmp_path / "review.pptx"
    _write_ooxml(derived, "ppt/slides/slide1.xml", "월간 품질 리뷰")
    document = _document(source, SignatureKind.OLE_SLIDE)

    result = NormalizeOffice(FakeOfficeNormalizer(derived=derived)).execute(document)

    assert result.failure_reason is None
    assert result.derived_path == derived
    assert source.exists()
    assert result.metadata is not None
    assert result.metadata.converted_from is DocumentFormat.PPT
    assert result.metadata.converter == "libreoffice"


def test_missing_soffice_fails_and_leaves_original(tmp_path: Path) -> None:
    source = _ole_doc(tmp_path / "legacy.doc")
    document = _document(source, SignatureKind.OLE_WORD)

    result = NormalizeOffice(FakeOfficeNormalizer(error=SofficeMissing())).execute(
        document
    )

    assert result.failure_reason is FailureReason.SOFFICE_MISSING
    assert result.derived_path is None
    assert source.exists()


def test_hangul_replacement_squares_fail_and_leave_original(tmp_path: Path) -> None:
    source = _ole_doc(tmp_path / "legacy.doc")
    original = source.read_bytes()

    def write_mojibake(
        _source: Path, output_dir: Path, _source_format: DocumentFormat
    ) -> Path:
        derived = output_dir / "legacy.docx"
        _write_ooxml(derived, "word/document.xml", "품번 □□ 대책")
        return derived

    document = _document(source, SignatureKind.OLE_WORD)
    result = NormalizeOffice(FakeOfficeNormalizer(writer=write_mojibake)).execute(
        document
    )

    assert result.failure_reason is FailureReason.MOJIBAKE
    assert result.derived_path is None
    assert source.exists()
    assert source.read_bytes() == original


def test_timeout_does_not_stop_later_files(tmp_path: Path) -> None:
    hanging = _ole_doc(tmp_path / "hang.doc")
    ok_source = _ole_doc(tmp_path / "ok.doc")
    ok_derived = tmp_path / "ok.docx"
    _write_ooxml(ok_derived, "word/document.xml", "원인")

    class MixedNormalizer:
        def convert(
            self,
            source: Path,
            output_dir: Path,
            *,
            source_format: DocumentFormat,
            timeout_seconds: float,
        ) -> Path:
            if source.name == "hang.doc":
                raise ConversionTimeout()
            return ok_derived

    uc = NormalizeOffice(MixedNormalizer())
    first = uc.execute(_document(hanging, SignatureKind.OLE_WORD))
    second = uc.execute(_document(ok_source, SignatureKind.OLE_WORD))

    assert first.failure_reason is FailureReason.HANG
    assert hanging.exists()
    assert second.failure_reason is None
    assert second.derived_path == ok_derived
    assert [item.source_path for item in uc.failure_queue] == [hanging]


def test_rejects_antiword_catdoc_and_python_bindings() -> None:
    now = datetime.now(UTC)
    for converter in ("antiword", "catdoc", "catppt", "python-docx", "python-pptx"):
        with pytest.raises(UnsupportedConverterError):
            ConversionMetadata(
                converted_from=DocumentFormat.DOC,
                converter=converter,
                converted_at=now,
            )


def test_doc_and_ppt_targets_are_ooxml_not_pdf() -> None:
    assert modern_office_target(DocumentFormat.DOC) is DocumentFormat.DOCX
    assert modern_office_target(DocumentFormat.PPT) is DocumentFormat.PPTX
    with pytest.raises(UnsupportedConverterError):
        modern_office_target(DocumentFormat.PDF)


def test_soffice_filters_are_modern_ooxml_not_pdf() -> None:
    assert soffice_filter(DocumentFormat.DOC) == "docx:MS Word 2007 XML"
    assert soffice_filter(DocumentFormat.PPT) == "pptx:Impress MS PowerPoint 2007 XML"
    assert '"' not in soffice_filter(DocumentFormat.DOC)
    assert '"' not in soffice_filter(DocumentFormat.PPT)
    assert "pdf" not in soffice_filter(DocumentFormat.DOC).lower()
    assert "pdf" not in soffice_filter(DocumentFormat.PPT).lower()


def test_adapter_does_not_hide_soffice_behind_docling_or_legacy_tools() -> None:
    import inspect

    module = inspect.getmodule(LibreOfficeNormalizer)
    assert module is not None
    source = inspect.getsource(module)
    assert "convert_to_modern_format" not in source
    assert "antiword" not in source
    assert "catdoc" not in source
    assert "catppt" not in source
    assert "python-docx" not in source
    assert "python-pptx" not in source
    assert "UserInstallation" in source
    assert "timeout" in source
    assert "MacroSecurityLevel" in source
    assert "DisableMacrosExecution" in source
