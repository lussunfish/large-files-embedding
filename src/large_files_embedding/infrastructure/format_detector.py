"""Signature-based format detector (magic bytes, not file extension)."""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterable
from pathlib import Path

from large_files_embedding.domain.document import FileSignature, SignatureKind

_OLE_MAGIC = bytes.fromhex("D0CF11E0A1B11AE1")
_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"
_TEXT_PREFIX = 65_536
_OLE_PREFIX = 1_048_576


class MagicFormatDetector:
    def detect(self, path: Path) -> FileSignature:
        with path.open("rb") as fh:
            head = fh.read(8)
            if not head:
                return FileSignature(SignatureKind.UNKNOWN)
            if head.startswith(b"%PDF"):
                return FileSignature(SignatureKind.PDF)
            if head.startswith(b"PK"):
                return _detect_zip(path)
            if head.startswith(_OLE_MAGIC):
                prefix = head + fh.read(_OLE_PREFIX - len(head))
                return _detect_ole(prefix)
            if head.startswith(_PNG_MAGIC) or head.startswith(_JPEG_MAGIC):
                return FileSignature(SignatureKind.UNSUPPORTED)
            prefix = head + fh.read(_TEXT_PREFIX - len(head))
        return _detect_text(prefix)


def _detect_zip(path: Path) -> FileSignature:
    try:
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile:
        return FileSignature(SignatureKind.UNKNOWN)
    if any(name.startswith("word/") for name in names):
        return FileSignature(SignatureKind.OOXML_WORD)
    if any(name.startswith("xl/") for name in names):
        return FileSignature(SignatureKind.OOXML_SHEET)
    if any(name.startswith("ppt/") for name in names):
        return FileSignature(SignatureKind.OOXML_SLIDE)
    return FileSignature(SignatureKind.UNSUPPORTED)


def _utf16(label: str) -> bytes:
    return label.encode("utf-16le")


def _ole_entry_name(label: str) -> bytes:
    """CFB directory entry name: UTF-16LE with null terminator."""
    return _utf16(label) + b"\x00\x00"


def _detect_ole(prefix: bytes) -> FileSignature:
    if b"HWP Document File" in prefix or _utf16("HwpSummaryInformation") in prefix:
        return FileSignature(SignatureKind.UNSUPPORTED)
    # Embedded Workbook/Book in .ppt must not win over the slide container.
    if _utf16("WordDocument") in prefix:
        return FileSignature(SignatureKind.OLE_WORD)
    if _utf16("PowerPoint Document") in prefix:
        return FileSignature(SignatureKind.OLE_SLIDE)
    if _utf16("Workbook") in prefix:
        return FileSignature(SignatureKind.OLE_SHEET)
    if _ole_entry_name("Book") in prefix:
        return FileSignature(SignatureKind.OLE_SHEET)
    return FileSignature(SignatureKind.UNSUPPORTED)


def _detect_text(prefix: bytes) -> FileSignature:
    stripped = prefix.lstrip(b"\xef\xbb\xbf \t\r\n")
    if stripped.startswith(b"{\\rtf"):
        return FileSignature(SignatureKind.RTF)
    if b"\x00" in prefix[:1024]:
        return FileSignature(SignatureKind.UNKNOWN)
    if _looks_like_json_or_xml(stripped):
        return FileSignature(SignatureKind.UNSUPPORTED)
    text = _decode_text(prefix)
    column_count = _csv_column_count(text)
    if column_count is None:
        return FileSignature(SignatureKind.UNKNOWN)
    return FileSignature(SignatureKind.CSV, csv_column_count=column_count)


def _looks_like_json_or_xml(stripped: bytes) -> bool:
    if stripped.startswith((b"{", b"[")):
        return True
    if stripped.startswith((b"<?xml", b"<!DOCTYPE")):
        return True
    if stripped.startswith(b"<") and len(stripped) > 1:
        nxt = stripped[1]
        return chr(nxt).isalpha() or nxt in {ord("/"), ord("!"), ord("?")}
    return False


def _decode_text(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _csv_column_count(text: str) -> int | None:
    sample_lines = [line for line in text.splitlines()[:40] if line.strip()]
    if not sample_lines:
        return None
    sample = "\n".join(sample_lines)
    candidates: list[int] = []
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = None
    if dialect is not None:
        sniffed = _column_mode(csv.reader(io.StringIO(sample), dialect))
        if sniffed is not None:
            candidates.append(sniffed)
    for delimiter in (",", ";", "\t"):
        counted = _column_mode(csv.reader(io.StringIO(sample), delimiter=delimiter))
        if counted is not None:
            candidates.append(counted)
    multi = [count for count in candidates if count >= 2]
    if multi:
        return max(multi)
    return 1


def _column_mode(rows: Iterable[list[str]]) -> int | None:
    counts = [len(row) for row in rows if any(cell.strip() for cell in row)]
    if not counts:
        return None
    mode = max(set(counts), key=counts.count)
    consistent = sum(1 for count in counts if count == mode)
    if consistent < max(1, int(len(counts) * 0.6)):
        return None
    return mode
