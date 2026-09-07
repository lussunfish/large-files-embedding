"""Sheet-level calamine/polars extractor for family C workbooks and CSV."""

from __future__ import annotations

import os
import re
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

from large_files_embedding.domain.document import (
    CALAMINE_ENGINE,
    ExtractedTabular,
    FactBatch,
    FailureReason,
    Grain,
    Layer1Sheet,
    SheetKind,
    SheetProfile,
    TabularIngestError,
    TabularProfile,
    infer_fact_mapping,
    is_cause_column,
    is_countermeasure_column,
    map_fact_column,
)

_DATE_COL_RE = re.compile(r"일|date|일자|발생|period", re.IGNORECASE)
_FACT_BATCH_ROWS = 5_000
_HEADER_LOOKAHEAD = 5


class CalamineTabularExtractor:
    def extract(self, path: Path, *, doc_id: str) -> ExtractedTabular:
        del doc_id
        suffix = path.suffix.lower()
        try:
            if suffix == ".csv":
                return _extract_csv(path)
            return _extract_excel(path)
        except TabularIngestError:
            raise
        except Exception as exc:
            raise TabularIngestError(FailureReason.EXTRACT_FAILED) from exc

    def iter_fact_slices(
        self, batch: FactBatch
    ) -> Iterator[Sequence[Mapping[str, object]]]:
        if batch.rows:
            yield list(batch.rows)
            return
        path = batch.parquet_path
        if path is None:
            return
        lazy = pl.scan_parquet(path)
        height = int(lazy.select(pl.len()).collect().item())
        for offset in range(0, height, _FACT_BATCH_ROWS):
            chunk = lazy.slice(offset, _FACT_BATCH_ROWS).collect()
            mapped = _map_facts(
                chunk, mapping=batch.table, report_period=batch.report_period
            )
            del chunk
            if mapped:
                yield mapped
            del mapped


def report_period_from_name(name: str) -> str | None:
    match = re.search(r"(20\d{2})[-_./년]?\s*(0?[1-9]|1[0-2])", name)
    if not match:
        return None
    return f"{match.group(1)}-{int(match.group(2)):02d}"


def _extract_excel(path: Path) -> ExtractedTabular:
    last_error: Exception | None = None
    try:
        return _extract_excel_fastexcel(path)
    except TabularIngestError:
        raise
    except Exception as exc:
        last_error = exc
    try:
        return _extract_excel_calamine(path)
    except Exception as exc:
        last_error = exc
    raise TabularIngestError(FailureReason.EXTRACT_FAILED) from last_error


def _extract_excel_fastexcel(path: Path) -> ExtractedTabular:
    import fastexcel

    reader = fastexcel.read_excel(str(path))
    names = list(reader.sheet_names)
    if not names:
        raise TabularIngestError(FailureReason.EXTRACT_FAILED)

    def load(name: str) -> pl.DataFrame:
        try:
            table = reader.load_sheet(name, header_row=None)
            return table.to_polars()
        except Exception:
            return pl.DataFrame()

    return _extract_named_sheets(path, names, load)


def _extract_excel_calamine(path: Path) -> ExtractedTabular:
    from python_calamine import CalamineWorkbook

    workbook = CalamineWorkbook.from_path(str(path))
    names = list(workbook.sheet_names)
    if not names:
        raise TabularIngestError(FailureReason.EXTRACT_FAILED)

    def load(name: str) -> pl.DataFrame:
        try:
            rows = workbook.get_sheet_by_name(name).to_python(skip_empty_area=False)
        except Exception:
            return pl.DataFrame()
        return _rows_to_raw_df(rows)

    return _extract_named_sheets(path, names, load)


def _extract_named_sheets(
    path: Path,
    names: list[str],
    load: Callable[[str], pl.DataFrame],
) -> ExtractedTabular:
    ingested_at = datetime.now(UTC)
    period = report_period_from_name(path.name)
    builder = _WorkbookBuilder(path.name, ingested_at, period)
    for name in names:
        kind = _kind_from_name(name)
        if kind is not SheetKind.DATA:
            builder.add_skipped(name, kind)
            continue
        frame = load(name)
        builder.add_data_sheet(name, frame)
        del frame
    return builder.finish()


def _extract_csv(path: Path) -> ExtractedTabular:
    encoding = _detect_encoding(path)
    sample_text = _decoded_sample(path, encoding)
    delimiter = _sniff_delimiter(sample_text)
    skip_rows = _csv_skip_rows(sample_text, delimiter)
    utf8_path: Path | None = None
    padded_path: Path | None = None
    scan_path = path
    try:
        if encoding not in {"utf-8", "utf8"}:
            utf8_path = _transcode_to_utf8(path, encoding)
            scan_path = utf8_path
        if _leading_blank_rows(sample_text) or _looks_fixed_width_padded(sample_text):
            padded_path = _rstrip_csv_lines(
                scan_path,
                encoding="utf-8" if utf8_path is not None else encoding,
            )
            scan_path = padded_path
            skip_rows = _csv_skip_rows(_decoded_sample(scan_path, "utf-8"), delimiter)
        lf = pl.scan_csv(
            scan_path,
            separator=delimiter,
            encoding="utf8",
            infer_schema_length=1000,
            try_parse_dates=False,
            skip_rows=skip_rows,
            truncate_ragged_lines=True,
        )
        raw_names = list(lf.collect_schema().names())
        unique = _unique_names(
            [
                str(name).lstrip("\ufeff").strip() or f"col_{index}"
                for index, name in enumerate(raw_names)
            ]
        )
        rename = {
            old: new for old, new in zip(raw_names, unique, strict=True) if old != new
        }
        if rename:
            lf = lf.rename(rename)
        sample = lf.head(5).collect()
        original_columns = tuple(str(col) for col in (sample.columns or unique))
        ingested_at = datetime.now(UTC)
        period = report_period_from_name(path.name)
        mapping = infer_fact_mapping(original_columns)
        template_family = _template_family(mapping)
        lf = _with_meta_lazy(
            lf,
            source_file=path.name,
            sheet_name=path.stem or "csv",
            report_period=period,
            ingested_at=ingested_at,
            template_family=template_family,
        )
        parquet_path = _sink_parquet(lf)
        n_rows = int(pl.scan_parquet(parquet_path).select(pl.len()).collect().item())
        kind = SheetKind.EMPTY if n_rows == 0 else SheetKind.DATA
        profile = SheetProfile(
            name=path.stem or "csv",
            kind=kind,
            n_rows=n_rows,
            n_cols=len(original_columns),
            header_candidates=original_columns,
            types=tuple(
                (col, str(sample.schema.get(col, "Unknown")))
                for col in original_columns
            ),
            nulls=tuple(
                (
                    col,
                    float(sample[col].null_count() / sample.height)
                    if sample.height
                    else 0.0,
                )
                for col in original_columns
                if col in sample.columns
            ),
            sample_rows=_sample_rows(sample),
            original_columns=original_columns,
        )
        grain = _grain(mapping)
        fact_batches: tuple[FactBatch, ...] = ()
        if kind is SheetKind.DATA and mapping:
            fact_batches = (
                FactBatch(
                    table=mapping,
                    grain=grain,
                    report_period=period,
                    parquet_path=parquet_path,
                ),
            )
        catalog = _catalog(mapping if fact_batches else None)
        return ExtractedTabular(
            profile=TabularProfile(
                source_file=path.name,
                sheets=(profile,),
                encoding=encoding,
                delimiter=delimiter,
            ),
            sheets=(
                Layer1Sheet(
                    sheet_name=path.stem or "csv",
                    parquet_bytes=None,
                    parquet_path=parquet_path if kind is SheetKind.DATA else None,
                    original_columns=original_columns,
                    report_period=period,
                    template_family=template_family,
                    ingested_at=ingested_at,
                    source_file=path.name,
                    n_rows=n_rows,
                    kind=kind,
                ),
            ),
            fact_batches=fact_batches,
            engine=CALAMINE_ENGINE,
            row_embedding_texts=(),
            catalog_sentences=catalog,
        )
    finally:
        if utf8_path is not None:
            utf8_path.unlink(missing_ok=True)
        if padded_path is not None:
            padded_path.unlink(missing_ok=True)


class _WorkbookBuilder:
    def __init__(
        self, source_file: str, ingested_at: datetime, period: str | None
    ) -> None:
        self._source_file = source_file
        self._ingested_at = ingested_at
        self._period = period
        self._profiles: list[SheetProfile] = []
        self._sheets: list[Layer1Sheet] = []
        self._batches: list[FactBatch] = []

    def add_skipped(self, name: str, kind: SheetKind) -> None:
        self._profiles.append(
            SheetProfile(
                name=name,
                kind=kind,
                n_rows=0,
                n_cols=0,
                header_candidates=(),
                types=(),
                nulls=(),
                sample_rows=(),
                original_columns=(),
            )
        )
        self._sheets.append(
            Layer1Sheet(
                sheet_name=name,
                parquet_bytes=None,
                parquet_path=None,
                original_columns=(),
                report_period=self._period,
                template_family=Grain.UNKNOWN.value,
                ingested_at=self._ingested_at,
                source_file=self._source_file,
                n_rows=0,
                kind=kind,
            )
        )

    def add_data_sheet(self, name: str, frame: pl.DataFrame) -> None:
        promoted, candidates, confident = _apply_header_detection(frame)
        kind = _classify_frame(name, promoted)
        if kind is not SheetKind.DATA:
            self.add_skipped(name, kind)
            return
        converted = _convert_date_columns(promoted)
        original_columns = tuple(str(col) for col in converted.columns)
        mapping = infer_fact_mapping(original_columns) if confident else None
        template_family = _template_family(mapping)
        sheet_period = self._period or _period_from_frame(converted)
        n_rows = converted.height
        self._profiles.append(
            _sheet_profile(name, kind, converted, original_columns, candidates)
        )
        parquet_path = _write_parquet(
            converted,
            source_file=self._source_file,
            sheet_name=name,
            report_period=sheet_period,
            ingested_at=self._ingested_at,
            template_family=template_family,
        )
        del converted
        self._sheets.append(
            Layer1Sheet(
                sheet_name=name,
                parquet_bytes=None,
                parquet_path=parquet_path,
                original_columns=original_columns,
                report_period=sheet_period,
                template_family=template_family,
                ingested_at=self._ingested_at,
                source_file=self._source_file,
                n_rows=n_rows,
                kind=kind,
            )
        )
        if mapping:
            self._batches.append(
                FactBatch(
                    table=mapping,
                    grain=_grain(mapping),
                    report_period=sheet_period,
                    parquet_path=parquet_path,
                )
            )

    def finish(self) -> ExtractedTabular:
        tables = list(dict.fromkeys(batch.table for batch in self._batches))
        catalog = _catalog(tables[0] if len(tables) == 1 else None)
        if len(tables) > 1:
            catalog = (
                "claim_event 한 행 = 클레임 1건",
                "monthly_quality_kpi 한 행 = 월보 스냅샷 1건",
            )
        return ExtractedTabular(
            profile=TabularProfile(
                source_file=self._source_file,
                sheets=tuple(self._profiles),
            ),
            sheets=tuple(self._sheets),
            fact_batches=tuple(self._batches),
            engine=CALAMINE_ENGINE,
            row_embedding_texts=(),
            catalog_sentences=catalog,
        )


def _rows_to_raw_df(rows: list[Any]) -> pl.DataFrame:
    if not rows:
        return pl.DataFrame()
    width = max((len(row) for row in rows), default=0)
    columns: dict[str, list[object]] = {f"c{index}": [] for index in range(width)}
    for row in rows:
        for index in range(width):
            columns[f"c{index}"].append(row[index] if index < len(row) else None)
    return pl.DataFrame(columns)


def _apply_header_detection(
    frame: pl.DataFrame,
) -> tuple[pl.DataFrame, tuple[str, ...], bool]:
    if frame.is_empty() or frame.width == 0:
        return frame, (), False
    candidates: list[str] = []
    for index in range(min(3, frame.height)):
        for cell in frame.row(index):
            text = "" if cell is None else str(cell).strip()
            if text:
                candidates.append(text)
    header_idx = 0
    confident = False
    for index in range(min(_HEADER_LOOKAHEAD, frame.height)):
        values = list(frame.row(index))
        if _looks_like_header(values):
            header_idx = index
            confident = True
            break
    names = _unique_names(
        [_cell_name(cell, index) for index, cell in enumerate(frame.row(header_idx))]
    )
    body = frame.slice(header_idx + 1)
    if body.is_empty():
        return pl.DataFrame({name: [] for name in names}), tuple(candidates), confident
    old = list(body.columns)
    width = min(len(names), len(old))
    selected = old[:width]
    renamed = {selected[index]: names[index] for index in range(width)}
    return (
        body.select(selected).rename(renamed),
        tuple(dict.fromkeys(candidates)),
        confident,
    )


def _looks_like_header(values: Sequence[object]) -> bool:
    texts = [
        str(cell).strip() for cell in values if cell is not None and str(cell).strip()
    ]
    if len(texts) < 2:
        return False
    if infer_fact_mapping(texts) is not None:
        return True
    hits = 0
    for text in texts:
        if (
            is_cause_column(text)
            or is_countermeasure_column(text)
            or any(token in text for token in ("품번", "차종", "건수", "PPM", "ppm"))
        ):
            hits += 1
    return hits >= 2


def _cell_name(value: object, index: int) -> str:
    text = "" if value is None else str(value).strip()
    return text or f"col_{index}"


def _unique_names(names: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    unique: list[str] = []
    for name in names:
        count = seen.get(name, 0)
        unique.append(name if count == 0 else f"{name}_{count}")
        seen[name] = count + 1
    return unique


def _kind_from_name(name: str) -> SheetKind:
    lowered = name.lower()
    if "pivot" in lowered or "피벗" in name:
        return SheetKind.PIVOT
    if "chart" in lowered or "차트" in name:
        return SheetKind.CHART
    if "macro" in lowered or "매크로" in name or lowered.startswith("vba"):
        return SheetKind.MACRO
    return SheetKind.DATA


def _classify_frame(name: str, frame: pl.DataFrame) -> SheetKind:
    named = _kind_from_name(name)
    if named is not SheetKind.DATA:
        return named
    if frame.is_empty() or frame.width == 0 or frame.height == 0:
        return SheetKind.EMPTY
    if all(frame[col].null_count() == frame.height for col in frame.columns):
        return SheetKind.EMPTY
    return SheetKind.DATA


def _sheet_profile(
    name: str,
    kind: SheetKind,
    frame: pl.DataFrame,
    original_columns: tuple[str, ...],
    candidates: tuple[str, ...],
) -> SheetProfile:
    n_rows = frame.height if kind is SheetKind.DATA else 0
    headers = candidates or original_columns
    types = tuple(
        (col, str(frame.schema[col]))
        for col in original_columns
        if col in frame.columns
    )
    nulls = tuple(
        (
            col,
            float(frame[col].null_count() / frame.height) if frame.height else 0.0,
        )
        for col in original_columns
        if col in frame.columns
    )
    return SheetProfile(
        name=name,
        kind=kind,
        n_rows=n_rows,
        n_cols=len(original_columns),
        header_candidates=headers,
        types=types,
        nulls=nulls,
        sample_rows=_sample_rows(frame) if kind is SheetKind.DATA else (),
        original_columns=original_columns,
    )


def _sample_rows(frame: pl.DataFrame) -> tuple[tuple[str, ...], ...]:
    sample: list[tuple[str, ...]] = []
    if frame.height:
        for row in frame.head(5).iter_rows():
            sample.append(tuple("" if cell is None else str(cell) for cell in row))
    return tuple(sample)


def _convert_date_columns(frame: pl.DataFrame) -> pl.DataFrame:
    if frame.is_empty():
        return frame
    exprs: list[pl.Expr] = []
    for column in frame.columns:
        if not _DATE_COL_RE.search(column):
            continue
        dtype = frame.schema[column]
        if dtype in (pl.Date, pl.Datetime):
            exprs.append(pl.col(column).cast(pl.String).alias(column))
            continue
        serial = pl.col(column).cast(pl.Float64, strict=False)
        converted = (
            pl.date(1899, 12, 30)
            + pl.duration(days=serial.cast(pl.Int64, strict=False))
        ).dt.strftime("%Y-%m-%d")
        exprs.append(
            pl.when((serial >= 20_000) & (serial <= 80_000))
            .then(converted)
            .otherwise(pl.col(column).cast(pl.String, strict=False))
            .alias(column)
        )
    if not exprs:
        return frame
    return frame.with_columns(exprs)


def _write_parquet(
    frame: pl.DataFrame,
    *,
    source_file: str,
    sheet_name: str,
    report_period: str | None,
    ingested_at: datetime,
    template_family: str,
) -> Path:
    landing = frame.with_columns(
        pl.lit(source_file).alias("source_file"),
        pl.lit(sheet_name).alias("sheet_name"),
        pl.lit(report_period).alias("report_period"),
        pl.lit(ingested_at.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")).alias(
            "ingested_at"
        ),
        pl.lit(template_family).alias("template_family"),
    )
    handle, name = tempfile.mkstemp(prefix="layer1-", suffix=".parquet")
    os.close(handle)
    out = Path(name)
    out.unlink(missing_ok=True)
    landing.lazy().sink_parquet(out)
    return out


def _with_meta_lazy(
    frame: pl.LazyFrame,
    *,
    source_file: str,
    sheet_name: str,
    report_period: str | None,
    ingested_at: datetime,
    template_family: str,
) -> pl.LazyFrame:
    return frame.with_columns(
        pl.lit(source_file).alias("source_file"),
        pl.lit(sheet_name).alias("sheet_name"),
        pl.lit(report_period).alias("report_period"),
        pl.lit(ingested_at.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")).alias(
            "ingested_at"
        ),
        pl.lit(template_family).alias("template_family"),
    )


def _sink_parquet(frame: pl.LazyFrame) -> Path:
    handle, name = tempfile.mkstemp(prefix="layer1-", suffix=".parquet")
    os.close(handle)
    out = Path(name)
    out.unlink(missing_ok=True)
    frame.sink_parquet(out)
    return out


def _map_facts(
    frame: pl.DataFrame,
    *,
    mapping: str,
    report_period: str | None,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in frame.iter_rows(named=True):
        mapped: dict[str, object] = {
            "source_file": record.get("source_file"),
            "sheet_name": record.get("sheet_name"),
            "report_period": record.get("report_period") or report_period,
            "ingested_at": record.get("ingested_at"),
            "template_family": record.get("template_family"),
        }
        for column, value in record.items():
            target = map_fact_column(str(column), mapping)
            if target is None:
                continue
            mapped[target] = value
        rows.append(mapped)
    return rows


def _template_family(mapping: str | None) -> str:
    if mapping == "claim_event":
        return Grain.LEDGER.value
    if mapping == "monthly_quality_kpi":
        return Grain.SNAPSHOT.value
    return Grain.UNKNOWN.value


def _grain(mapping: str | None) -> Grain:
    if mapping == "claim_event":
        return Grain.LEDGER
    if mapping == "monthly_quality_kpi":
        return Grain.SNAPSHOT
    return Grain.UNKNOWN


def _catalog(mapping: str | None) -> tuple[str, ...]:
    if mapping == "claim_event":
        return ("claim_event 한 행 = 클레임 1건",)
    if mapping == "monthly_quality_kpi":
        return ("monthly_quality_kpi 한 행 = 월보 스냅샷 1건",)
    return ()


def _period_from_frame(frame: pl.DataFrame) -> str | None:
    for column in frame.columns:
        lowered = column.lower()
        if column in {"월", "기간"} or lowered in {"period", "month", "report_period"}:
            sample = frame.select(pl.col(column).drop_nulls().head(1))
            if sample.height:
                return str(sample.item())
    return None


def _csv_skip_rows(sample: str, delimiter: str) -> int:
    lines = [line for line in sample.splitlines() if line.strip()]
    if len(lines) < 2:
        return 0
    first = lines[0].split(delimiter)
    second = lines[1].split(delimiter)
    if not _looks_like_header(first) and _looks_like_header(second):
        return 1
    return 0


def _leading_blank_rows(sample: str) -> int:
    count = 0
    for line in sample.splitlines():
        if line.strip():
            break
        count += 1
    return count


def _looks_fixed_width_padded(sample: str) -> bool:
    lines = [line.rstrip("\n\r") for line in sample.splitlines() if line.strip()]
    if len(lines) < 2:
        return False
    widths = {len(line) for line in lines[:20]}
    if len(widths) != 1:
        return False
    width = next(iter(widths))
    if width < 40:
        return False
    return any(line.endswith("  ") for line in lines[:20])


def _rstrip_csv_lines(path: Path, *, encoding: str) -> Path:
    handle, name = tempfile.mkstemp(prefix="csv-rstrip-", suffix=".csv")
    out = Path(name)
    leading = True
    try:
        with (
            path.open("r", encoding=encoding, newline="") as src,
            os.fdopen(handle, "w", encoding="utf-8", newline="") as dst,
        ):
            for line in src:
                body = line.rstrip("\n\r").rstrip(" \t")
                if leading and not body:
                    continue
                leading = False
                dst.write(body)
                dst.write("\n")
    except Exception:
        out.unlink(missing_ok=True)
        raise
    return out


def _detect_encoding(path: Path) -> str:
    with path.open("rb") as fh:
        sample = fh.read(65_536)
    if sample.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        sample.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        try:
            sample.decode("cp949")
            return "cp949"
        except UnicodeDecodeError as exc:
            raise TabularIngestError(FailureReason.EXTRACT_FAILED) from exc


def _decoded_sample(path: Path, encoding: str) -> str:
    with path.open("rb") as fh:
        sample = fh.read(65_536)
    return sample.decode(encoding, errors="replace")


def _sniff_delimiter(sample: str) -> str:
    line = next((row for row in sample.splitlines() if row.strip()), "")
    counts = {",": line.count(","), ";": line.count(";"), "\t": line.count("\t")}
    best = max(counts, key=lambda key: counts[key])
    return best if counts[best] else ","


def _transcode_to_utf8(path: Path, encoding: str) -> Path:
    handle, name = tempfile.mkstemp(prefix="csv-utf8-", suffix=".csv")
    out = Path(name)
    with (
        path.open("r", encoding=encoding, newline="") as src,
        os.fdopen(handle, "w", encoding="utf-8", newline="") as dst,
    ):
        while True:
            chunk = src.read(1_048_576)
            if not chunk:
                break
            dst.write(chunk)
    return out
