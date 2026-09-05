"""Normalize OLE .doc/.ppt to modern OOXML without deleting the original."""

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from large_files_embedding.domain.document import (
    DEFAULT_OFFICE_TIMEOUT_SECONDS,
    LIBREOFFICE_CONVERTER,
    ConversionFailed,
    ConversionMetadata,
    ConversionTimeout,
    Document,
    FailureReason,
    NormalizationError,
    NormalizationResult,
    OfficeNormalizer,
    SofficeMissing,
    UnsupportedConverterError,
    has_broken_hangul,
    modern_office_target,
)


class NormalizeOffice:
    def __init__(
        self,
        normalizer: OfficeNormalizer,
        *,
        timeout_seconds: float = DEFAULT_OFFICE_TIMEOUT_SECONDS,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._normalizer = normalizer
        self._timeout_seconds = timeout_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        self.failure_queue: list[NormalizationResult] = []

    def execute(
        self, document: Document, output_dir: Path | None = None
    ) -> NormalizationResult:
        source = document.path
        dest = output_dir or source.parent
        dest.mkdir(parents=True, exist_ok=True)
        if document.decision is None or not document.decision.needs_normalization:
            return self._fail(source, FailureReason.UNSUPPORTED_CONVERTER)
        source_format = document.decision.detected_format
        try:
            modern_office_target(source_format)
        except UnsupportedConverterError:
            return self._fail(source, FailureReason.UNSUPPORTED_CONVERTER)
        try:
            derived = self._normalizer.convert(
                source,
                dest,
                source_format=source_format,
                timeout_seconds=self._timeout_seconds,
            )
        except (ConversionTimeout, TimeoutError):
            return self._fail(source, FailureReason.HANG)
        except SofficeMissing:
            return self._fail(source, FailureReason.SOFFICE_MISSING)
        except ConversionFailed as exc:
            return self._fail(source, exc.reason)
        except NormalizationError as exc:
            return self._fail(source, exc.reason)
        if not derived.exists():
            return self._fail(source, FailureReason.CONVERSION_FAILED)
        if has_broken_hangul(_ooxml_text(derived)):
            return self._fail(source, FailureReason.MOJIBAKE)
        metadata = ConversionMetadata(
            converted_from=source_format,
            converter=LIBREOFFICE_CONVERTER,
            converted_at=self._clock(),
        )
        return NormalizationResult(source, derived, metadata, None)

    def _fail(self, source: Path, reason: FailureReason) -> NormalizationResult:
        result = NormalizationResult(source, None, None, reason)
        self.failure_queue.append(result)
        return result


def _ooxml_text(path: Path) -> str:
    try:
        with ZipFile(path) as archive:
            parts = [
                archive.read(name).decode("utf-8", errors="replace")
                for name in archive.namelist()
                if name.endswith((".xml", ".rels"))
            ]
        return "\n".join(parts)
    except BadZipFile:
        return path.read_bytes().decode("utf-8", errors="replace")
