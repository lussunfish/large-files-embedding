"""LibreOffice soffice adapter: timeout + per-file UserInstallation."""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import tempfile
import threading
from pathlib import Path

from large_files_embedding.domain.document import (
    ConversionFailed,
    ConversionTimeout,
    DocumentFormat,
    SofficeMissing,
    modern_office_target,
    soffice_filter,
)

_ENV_CMD = "DOCLING_LIBREOFFICE_CMD"


class LibreOfficeNormalizer:
    _lock = threading.Lock()

    def convert(
        self,
        source: Path,
        output_dir: Path,
        *,
        source_format: DocumentFormat,
        timeout_seconds: float,
    ) -> Path:
        if timeout_seconds <= 0:
            raise ConversionTimeout()
        soffice = _resolve_soffice()
        output_dir.mkdir(parents=True, exist_ok=True)
        target = modern_office_target(source_format)
        derived = output_dir / f"{source.stem}.{target.value}"
        filter_spec = soffice_filter(source_format)
        with LibreOfficeNormalizer._lock:
            return _run_soffice(
                soffice=soffice,
                source=source,
                output_dir=output_dir,
                derived=derived,
                filter_spec=filter_spec,
                timeout_seconds=timeout_seconds,
            )


def _resolve_soffice() -> Path:
    configured = os.environ.get(_ENV_CMD, "").strip()
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return candidate
        found = shutil.which(configured)
        if found is not None:
            return Path(found)
        raise SofficeMissing()
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found is None:
        raise SofficeMissing()
    return Path(found)


def _run_soffice(
    *,
    soffice: Path,
    source: Path,
    output_dir: Path,
    derived: Path,
    filter_spec: str,
    timeout_seconds: float,
) -> Path:
    profile = Path(tempfile.mkdtemp(prefix=f"lo-{source.stem}-"))
    cmd = [
        str(soffice),
        "--headless",
        "--norestore",
        "--nolockcheck",
        f"-env:UserInstallation={profile.resolve().as_uri()}",
        "--convert-to",
        filter_spec,
        "--outdir",
        str(output_dir.resolve()),
        str(source.resolve()),
    ]
    try:
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
        except FileNotFoundError as exc:
            raise SofficeMissing() from exc
        try:
            proc.communicate(timeout=timeout_seconds)
        except subprocess.TimeoutExpired as exc:
            _kill_group(proc)
            raise ConversionTimeout() from exc
        if proc.returncode != 0 or not derived.exists():
            raise ConversionFailed()
        return derived
    finally:
        shutil.rmtree(profile, ignore_errors=True)


def _kill_group(proc: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError, OSError):
        proc.kill()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
