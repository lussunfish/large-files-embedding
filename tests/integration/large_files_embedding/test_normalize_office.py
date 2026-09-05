"""UC-02 integration: LibreOfficeNormalizer subprocess, timeout, CLI wiring."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import textwrap
from pathlib import Path
from zipfile import ZipFile

import pytest
from typer.testing import CliRunner

from large_files_embedding.application.normalize_office import NormalizeOffice
from large_files_embedding.domain.document import (
    ConversionTimeout,
    Document,
    DocumentFormat,
    FailureReason,
    FileSignature,
    SignatureKind,
    SofficeMissing,
)
from large_files_embedding.infrastructure.libreoffice_normalizer import (
    LibreOfficeNormalizer,
)
from large_files_embedding.presentation.cli.main import app

OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")

_FAKE_SOFFICE = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import sys
    from pathlib import Path
    from zipfile import ZipFile

    argv = sys.argv[1:]
    Path(__file__).with_suffix(".log").write_text("\\n".join(argv), encoding="utf-8")
    outdir = Path(argv[argv.index("--outdir") + 1])
    source = Path(argv[-1])
    convert_to = argv[argv.index("--convert-to") + 1]
    ext = "docx" if convert_to.startswith("docx") else "pptx"
    derived = outdir / f"{source.stem}.{ext}"
    inner = "word/document.xml" if ext == "docx" else "ppt/slides/slide1.xml"
    with ZipFile(derived, "w") as archive:
        archive.writestr(inner, "<t>원인과 대책</t>")
    """
)

_HANGING_SOFFICE = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import time
    time.sleep(30)
    """
)


def _ole(path: Path, stream: str) -> Path:
    path.write_bytes(OLE_MAGIC + b"\x00" * 256 + stream.encode("utf-16le"))
    return path


def _install_script(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


def test_adapter_timeout_is_hang_and_keeps_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _install_script(tmp_path / "hang_soffice", _HANGING_SOFFICE)
    monkeypatch.setenv("DOCLING_LIBREOFFICE_CMD", str(script))
    source = _ole(tmp_path / "legacy.doc", "WordDocument")
    original = source.read_bytes()

    with pytest.raises(ConversionTimeout):
        LibreOfficeNormalizer().convert(
            source,
            tmp_path,
            source_format=DocumentFormat.DOC,
            timeout_seconds=0.2,
        )

    assert source.exists()
    assert source.read_bytes() == original


def test_adapter_uses_user_installation_and_word_filter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _install_script(tmp_path / "fake_soffice", _FAKE_SOFFICE)
    monkeypatch.setenv("DOCLING_LIBREOFFICE_CMD", str(script))
    source = _ole(tmp_path / "claim_8d.doc", "WordDocument")
    derived = LibreOfficeNormalizer().convert(
        source,
        tmp_path,
        source_format=DocumentFormat.DOC,
        timeout_seconds=5,
    )
    log = Path(str(script) + ".log").read_text(encoding="utf-8")
    convert_to = log.split("\n")[log.split("\n").index("--convert-to") + 1]
    assert "UserInstallation=file://" in log
    assert convert_to == "docx:MS Word 2007 XML"
    assert '"' not in convert_to
    assert "--headless" in log
    assert "pdf" not in log.lower()
    assert derived.exists()
    assert source.exists()
    assert derived != source


def test_adapter_ppt_filter_is_pptx_not_pdf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _install_script(tmp_path / "fake_soffice", _FAKE_SOFFICE)
    monkeypatch.setenv("DOCLING_LIBREOFFICE_CMD", str(script))
    source = _ole(tmp_path / "review.ppt", "PowerPoint Document")
    derived = LibreOfficeNormalizer().convert(
        source,
        tmp_path,
        source_format=DocumentFormat.PPT,
        timeout_seconds=5,
    )
    log = Path(str(script) + ".log").read_text(encoding="utf-8")
    convert_to = log.split("\n")[log.split("\n").index("--convert-to") + 1]
    assert convert_to == "pptx:Impress MS PowerPoint 2007 XML"
    assert '"' not in convert_to
    assert "pdf" not in log.lower()
    assert derived.suffix == ".pptx"
    assert source.exists()


def test_missing_soffice_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DOCLING_LIBREOFFICE_CMD", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    (tmp_path / "empty-bin").mkdir()
    source = _ole(tmp_path / "legacy.doc", "WordDocument")
    with pytest.raises(SofficeMissing):
        LibreOfficeNormalizer().convert(
            source,
            tmp_path,
            source_format=DocumentFormat.DOC,
            timeout_seconds=1,
        )
    assert source.exists()


def test_use_case_timeout_via_adapter_leaves_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _install_script(tmp_path / "hang_soffice", _HANGING_SOFFICE)
    monkeypatch.setenv("DOCLING_LIBREOFFICE_CMD", str(script))
    source = _ole(tmp_path / "legacy.doc", "WordDocument")
    document = Document.from_signature(source, FileSignature(SignatureKind.OLE_WORD))
    result = NormalizeOffice(LibreOfficeNormalizer(), timeout_seconds=0.2).execute(
        document
    )
    assert result.failure_reason is FailureReason.HANG
    assert result.derived_path is None
    assert source.exists()


def test_ingest_cli_normalizes_ole_doc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    script = _install_script(tmp_path / "fake_soffice", _FAKE_SOFFICE)
    monkeypatch.setenv("DOCLING_LIBREOFFICE_CMD", str(script))
    source = _ole(tmp_path / "legacy.doc", "WordDocument")
    result = CliRunner().invoke(app, ["ingest", str(source)])
    assert result.exit_code == 0
    assert "derived=" in result.stdout
    assert "converter=libreoffice" in result.stdout
    assert "converted_from=doc" in result.stdout
    assert source.exists()
    assert (tmp_path / "legacy.docx").exists()


def test_ingest_cli_pdf_does_not_need_soffice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DOCLING_LIBREOFFICE_CMD", raising=False)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    (tmp_path / "empty-bin").mkdir()
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n%%EOF\n")
    result = CliRunner().invoke(app, ["ingest", str(pdf)])
    assert result.exit_code == 0
    assert "family=B" in result.stdout
    assert "soffice_missing" not in result.stdout


_PKG = "http://schemas.openxmlformats.org/package/2006"
_OD = "http://schemas.openxmlformats.org/officeDocument/2006"
_WML = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_RELS_TYPE = "application/vnd.openxmlformats-package.relationships+xml"
_DOCX_MAIN = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
)


def _write_minimal_docx(path: Path, text: str = "원인과 대책") -> Path:
    with ZipFile(path, "w") as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Types xmlns="{_PKG}/content-types">'
            f'<Default Extension="rels" ContentType="{_RELS_TYPE}"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" '
            f'ContentType="{_DOCX_MAIN}"/>'
            "</Types>",
        )
        archive.writestr(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{_PKG}/relationships">'
            '<Relationship Id="rId1" '
            f'Type="{_OD}/relationships/officeDocument" '
            'Target="word/document.xml"/>'
            "</Relationships>",
        )
        archive.writestr(
            "word/_rels/document.xml.rels",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{_PKG}/relationships"/>',
        )
        archive.writestr(
            "word/document.xml",
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<w:document xmlns:w="{_WML}">'
            f"<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>"
            "</w:document>",
        )
    return path


@pytest.mark.skipif(
    shutil.which("soffice") is None and shutil.which("libreoffice") is None,
    reason="soffice not installed",
)
def test_real_soffice_converts_doc_and_keeps_original(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DOCLING_LIBREOFFICE_CMD", raising=False)
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    assert soffice is not None
    seed = _write_minimal_docx(tmp_path / "seed.docx")
    ole_dir = tmp_path / "ole"
    ole_dir.mkdir()
    created = subprocess.run(
        [
            soffice,
            "--headless",
            "--norestore",
            "--nolockcheck",
            f"-env:UserInstallation={(tmp_path / 'lo-seed').resolve().as_uri()}",
            "--convert-to",
            "doc:MS Word 97",
            "--outdir",
            str(ole_dir),
            str(seed),
        ],
        check=False,
        capture_output=True,
        timeout=60,
    )
    source = ole_dir / "seed.doc"
    if created.returncode != 0 or not source.exists():
        stderr = created.stderr.decode("utf-8", errors="replace")
        pytest.fail(
            "soffice could not create a .doc fixture from docx "
            f"(rc={created.returncode}): {stderr}"
        )
    original = source.read_bytes()
    derived = LibreOfficeNormalizer().convert(
        source,
        tmp_path / "out",
        source_format=DocumentFormat.DOC,
        timeout_seconds=60,
    )
    assert source.exists()
    assert source.read_bytes() == original
    assert derived.exists()
    assert derived.suffix == ".docx"
    assert os.environ.get("DOCLING_LIBREOFFICE_CMD") is None
