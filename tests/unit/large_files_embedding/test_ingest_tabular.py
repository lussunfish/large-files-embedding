"""UC-04: ingest XLSX/XLS/CSV into Parquet + MariaDB (fake Ports)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from large_files_embedding.application.ingest_tabular import IngestTabular
from large_files_embedding.domain.document import (
    MARKET_QUALITY_COLLECTION,
    PROFILE_JSON_MAX_BYTES,
    Document,
    DocumentFormat,
    ExtractedTabular,
    FactBatch,
    FailureReason,
    FileSignature,
    Grain,
    Layer1Sheet,
    SheetKind,
    SheetProfile,
    SignatureKind,
    TabularIngestError,
    TabularProfile,
    convert_excel_serial,
    excel_serial_to_date,
    forbid_row_embedding,
    infer_fact_mapping,
    map_fact_column,
    require_cause_columns_kept,
    require_fact_table,
    require_original_columns,
    require_snapshot_period,
    validate_extracted_tabular,
)


class FakeTabularExtractor:
    def __init__(
        self,
        result: ExtractedTabular | None = None,
        error: Exception | None = None,
        *,
        xls_error: Exception | None = None,
        after_xls: ExtractedTabular | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.xls_error = xls_error
        self.after_xls = after_xls
        self.calls: list[Path] = []

    def extract(self, path: Path, *, doc_id: str) -> ExtractedTabular:
        del doc_id
        self.calls.append(path)
        if path.suffix.lower() == ".xls" and self.xls_error is not None:
            raise self.xls_error
        if self.error is not None:
            raise self.error
        if path.suffix.lower() != ".xls" and self.after_xls is not None:
            return self.after_xls
        assert self.result is not None
        return self.result

    def iter_fact_slices(self, batch: FactBatch):
        if batch.rows:
            yield list(batch.rows)


class FakeTableStore:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict[str, object]], Grain, str | None]] = []

    def insert_facts(
        self,
        table: str,
        rows: list[dict[str, object]],
        *,
        grain: Grain,
        report_period: str | None,
    ) -> int:
        require_fact_table(table)
        if grain is Grain.SNAPSHOT:
            require_snapshot_period(report_period)
        self.calls.append((table, list(rows), grain, report_period))
        return len(rows)


class FakeObjectStore:
    def __init__(self) -> None:
        self.bytes_objects: dict[str, bytes] = {}
        self.file_objects: dict[str, Path] = {}

    def put_bytes(self, key: str, body: bytes, *, content_type: str) -> None:
        del content_type
        self.bytes_objects[key] = body

    def put_file(self, key: str, path: Path, *, content_type: str) -> None:
        del content_type
        self.file_objects[key] = path


class FakeXlsFallback:
    def __init__(self, derived: Path) -> None:
        self.derived = derived
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
        dest = output_dir / f"{source.stem}.xlsx"
        payload = self.derived.read_bytes() if self.derived.exists() else b"xlsx"
        dest.write_bytes(payload)
        return dest


def _document(path: Path, kind: SignatureKind) -> Document:
    return Document.from_signature(path, FileSignature(kind))


def _sheet_profile(
    *,
    name: str = "원장",
    kind: SheetKind = SheetKind.DATA,
    columns: tuple[str, ...] = ("품번", "차종", "발생일", "원인", "대책", "건수"),
    n_rows: int = 2,
) -> SheetProfile:
    return SheetProfile(
        name=name,
        kind=kind,
        n_rows=n_rows,
        n_cols=len(columns),
        header_candidates=columns,
        types=tuple((col, "String") for col in columns),
        nulls=tuple((col, 0.0) for col in columns),
        sample_rows=(
            ("A-1", "SUV", "2024-01-15", "누유", "가스켓 교체", "3"),
            ("B-2", "SEDAN", "2024-02-01", "소음", "체결 재작업", "1"),
        )[: min(5, max(n_rows, 0))],
        original_columns=columns,
    )


def _layer1(
    *,
    sheet_name: str = "원장",
    columns: tuple[str, ...] = ("품번", "차종", "발생일", "원인", "대책", "건수"),
    parquet_bytes: bytes = b"PAR1",
    report_period: str | None = "2024-01",
    template_family: str = "ledger",
    kind: SheetKind = SheetKind.DATA,
    n_rows: int = 2,
    source_file: str = "ledger.xlsx",
) -> Layer1Sheet:
    return Layer1Sheet(
        sheet_name=sheet_name,
        parquet_bytes=parquet_bytes,
        parquet_path=None,
        original_columns=columns,
        report_period=report_period,
        template_family=template_family,
        ingested_at=datetime(2026, 1, 1, tzinfo=UTC),
        source_file=source_file,
        n_rows=n_rows,
        kind=kind,
    )


def _extracted(
    *,
    sheets: tuple[Layer1Sheet, ...] | None = None,
    profile_sheets: tuple[SheetProfile, ...] | None = None,
    fact_table: str | None = "claim_event",
    fact_rows: tuple[dict[str, object], ...] | None = None,
    grain: Grain = Grain.LEDGER,
    engine: str = "calamine",
    row_embedding_texts: tuple[str, ...] = (),
    source_file: str = "ledger.xlsx",
    fact_batches: tuple[FactBatch, ...] | None = None,
) -> ExtractedTabular:
    layer = sheets if sheets is not None else (_layer1(source_file=source_file),)
    profiles = profile_sheets if profile_sheets is not None else (_sheet_profile(),)
    rows = fact_rows
    if rows is None and fact_table == "claim_event" and fact_batches is None:
        rows = (
            {
                "source_file": source_file,
                "sheet_name": "원장",
                "report_period": "2024-01",
                "part_no": "A-1",
                "vehicle": "SUV",
                "cause": "누유",
                "countermeasure": "가스켓 교체",
                "quantity": 3,
            },
        )
    if rows is None:
        rows = ()
    if fact_batches is None:
        if fact_table and rows:
            period = next(
                (
                    sheet.report_period
                    for sheet in layer
                    if sheet.kind is SheetKind.DATA
                ),
                None,
            )
            fact_batches = (
                FactBatch(
                    table=fact_table, grain=grain, report_period=period, rows=rows
                ),
            )
        else:
            fact_batches = ()
    return ExtractedTabular(
        profile=TabularProfile(source_file=source_file, sheets=profiles),
        sheets=layer,
        fact_batches=fact_batches,
        engine=engine,
        row_embedding_texts=row_embedding_texts,
        catalog_sentences=("claim_event 한 행 = 클레임 1건",),
    )


def _uc(
    extractor: FakeTabularExtractor,
    tables: FakeTableStore | None = None,
    objects: FakeObjectStore | None = None,
    *,
    xls_fallback: FakeXlsFallback | None = None,
) -> tuple[IngestTabular, FakeTableStore, FakeObjectStore]:
    tables = tables or FakeTableStore()
    objects = objects or FakeObjectStore()
    return (
        IngestTabular(extractor, tables, objects, xls_fallback=xls_fallback),
        tables,
        objects,
    )


def test_wide_workbook_profile_json_is_clipped_under_limit() -> None:
    import json

    cols = tuple(f"GeneratorCol_{index:03d}" for index in range(80))
    sheet = SheetProfile(
        name="Operable",
        kind=SheetKind.DATA,
        n_rows=25000,
        n_cols=80,
        header_candidates=cols,
        types=tuple((col, "String") for col in cols),
        nulls=tuple((col, 0.1) for col in cols),
        sample_rows=(cols, cols, cols, cols, cols),
        original_columns=cols,
    )
    profile = TabularProfile(
        source_file="09-3_1_Generator_Y2022.xlsx",
        sheets=(sheet, sheet, sheet),
    )
    raw = profile.to_json_bytes()
    assert len(raw) <= PROFILE_JSON_MAX_BYTES
    payload = json.loads(raw.decode("utf-8"))
    assert payload["sheets"][0]["n_cols"] == 80
    extracted = _extracted(
        sheets=(_layer1(columns=cols, sheet_name="Operable"),),
        profile_sheets=(sheet,),
        fact_table=None,
        fact_rows=(),
        source_file="09-3_1_Generator_Y2022.xlsx",
    )
    validate_extracted_tabular(extracted)


def test_xlsx_row_embedding_request_raises_domain_exception() -> None:
    rows = ["품번 A-1 원인 누유", "품번 B-2 원인 소음"]
    with pytest.raises(TabularIngestError) as exc:
        forbid_row_embedding(rows)
    assert exc.value.reason is FailureReason.ROW_EMBEDDING


def test_deleting_cause_countermeasure_columns_is_rejected() -> None:
    with pytest.raises(TabularIngestError) as exc:
        require_cause_columns_kept(
            original_columns=("품번", "원인", "대책", "건수"),
            landing_columns=("품번", "건수"),
        )
    assert exc.value.reason is FailureReason.CAUSE_COLUMN_DROPPED


def test_english_cause_countermeasure_drop_is_rejected() -> None:
    with pytest.raises(TabularIngestError) as exc:
        require_cause_columns_kept(
            original_columns=("part_no", "cause", "countermeasure"),
            landing_columns=("part_no",),
        )
    assert exc.value.reason is FailureReason.CAUSE_COLUMN_DROPPED


def test_ingest_fails_when_extractor_requests_row_embedding() -> None:
    path = Path("ledger.xlsx")
    extractor = FakeTabularExtractor(
        _extracted(row_embedding_texts=("품번 A-1 원인 누유",))
    )
    uc, tables, objects = _uc(extractor)

    result = uc.execute(_document(path, SignatureKind.OOXML_SHEET))

    assert result.failed is True
    assert result.failure_reason is FailureReason.ROW_EMBEDDING
    assert tables.calls == []
    assert objects.bytes_objects == {}
    assert objects.file_objects == {}


def test_ingest_fails_when_layer1_drops_cause_columns() -> None:
    path = Path("ledger.xlsx")
    dropped = ("품번", "차종", "건수")
    extractor = FakeTabularExtractor(
        _extracted(
            sheets=(_layer1(columns=dropped),),
            fact_table=None,
            fact_rows=(),
        )
    )
    uc, tables, objects = _uc(extractor)

    result = uc.execute(_document(path, SignatureKind.OOXML_SHEET))

    assert result.failed is True
    assert result.failure_reason is FailureReason.CAUSE_COLUMN_DROPPED
    assert tables.calls == []
    assert objects.bytes_objects == {}


def test_ingest_stores_profile_parquet_and_not_vector_rows() -> None:
    path = Path("ledger.xlsx")
    extractor = FakeTabularExtractor(_extracted())
    uc, tables, objects = _uc(extractor)

    result = uc.execute(_document(path, SignatureKind.OOXML_SHEET))

    assert result.failed is False
    assert result.sheet_count == 1
    assert result.profile_key is not None
    assert result.profile_key.endswith("profile.json")
    assert result.parquet_keys
    profile = objects.bytes_objects[result.profile_key]
    assert 2 <= len(profile) <= 10 * 1024
    assert b"header_candidates" in profile
    assert b"sample_rows" in profile
    assert tables.calls and tables.calls[0][0] == "claim_event"
    fact_row = tables.calls[0][1][0]
    assert "cause" in fact_row
    assert "countermeasure" in fact_row
    assert MARKET_QUALITY_COLLECTION not in result.profile_key


def test_unmapped_file_stays_layer1_only() -> None:
    path = Path("misc.xlsx")
    columns = ("컬럼A", "컬럼B")
    extractor = FakeTabularExtractor(
        _extracted(
            sheets=(_layer1(columns=columns, source_file="misc.xlsx"),),
            profile_sheets=(_sheet_profile(columns=columns),),
            fact_table=None,
            fact_rows=(),
            grain=Grain.UNKNOWN,
            source_file="misc.xlsx",
        )
    )
    uc, tables, objects = _uc(extractor)

    result = uc.execute(_document(path, SignatureKind.OOXML_SHEET))

    assert result.failed is False
    assert result.fact_table is None
    assert result.fact_row_count == 0
    assert tables.calls == []
    assert any(key.endswith("profile.json") for key in objects.bytes_objects)
    assert result.parquet_keys


def test_snapshot_without_report_period_does_not_union() -> None:
    path = Path("monthly.xlsx")
    columns = ("차종", "클레임건수", "PPM")
    extractor = FakeTabularExtractor(
        _extracted(
            sheets=(
                _layer1(
                    columns=columns,
                    report_period=None,
                    template_family="snapshot",
                    source_file="monthly.xlsx",
                ),
            ),
            profile_sheets=(_sheet_profile(columns=columns),),
            fact_table="monthly_quality_kpi",
            fact_rows=(
                {
                    "source_file": "monthly.xlsx",
                    "sheet_name": "원장",
                    "vehicle": "SUV",
                    "claim_count": 3,
                    "ppm": 12.0,
                },
            ),
            grain=Grain.SNAPSHOT,
            source_file="monthly.xlsx",
        )
    )
    uc, tables, objects = _uc(extractor)

    result = uc.execute(_document(path, SignatureKind.OOXML_SHEET))

    assert result.failed is False
    assert result.fact_table is None
    assert tables.calls == []
    assert result.parquet_keys
    assert any(key.endswith("profile.json") for key in objects.bytes_objects)


def test_snapshot_insert_without_period_is_rejected_by_store() -> None:
    store = FakeTableStore()
    with pytest.raises(TabularIngestError) as exc:
        store.insert_facts(
            "monthly_quality_kpi",
            [{"vehicle": "SUV", "claim_count": 1}],
            grain=Grain.SNAPSHOT,
            report_period=None,
        )
    assert exc.value.reason is FailureReason.SNAPSHOT_UNION


def test_table_per_file_and_embeddings_vector_and_xlsx_blob_are_rejected() -> None:
    with pytest.raises(TabularIngestError) as per_file:
        require_fact_table("ledger_xlsx_원장")
    assert per_file.value.reason is FailureReason.TABLE_PER_FILE
    with pytest.raises(TabularIngestError) as chunks:
        require_fact_table("embeddings.chunks")
    assert chunks.value.reason is FailureReason.EMBEDDINGS_VECTOR
    with pytest.raises(TabularIngestError) as blob:
        require_fact_table("xlsx_blob")
    assert blob.value.reason is FailureReason.XLSX_BLOB


def test_xls_calamine_failure_uses_libreoffice_fallback(tmp_path: Path) -> None:
    source = tmp_path / "legacy.xls"
    source.write_bytes(b"ole")
    sibling = tmp_path / "legacy.xlsx"
    sibling.write_bytes(b"keep-sibling")
    derived = tmp_path / "converted.xlsx"
    derived.write_bytes(b"xlsx")
    fallback = FakeXlsFallback(derived)
    extractor = FakeTabularExtractor(
        xls_error=TabularIngestError(FailureReason.EXTRACT_FAILED),
        after_xls=_extracted(source_file="legacy.xls"),
    )
    uc, tables, _objects = _uc(extractor, xls_fallback=fallback)

    result = uc.execute(_document(source, SignatureKind.OLE_SHEET))

    assert result.failed is False
    assert extractor.calls[0] == source
    assert extractor.calls[-1].name == "legacy.xlsx"
    assert extractor.calls[-1].parent != source.parent
    assert fallback.calls
    assert fallback.calls[0][2] is DocumentFormat.XLS
    assert fallback.calls[0][1] != source.parent
    assert sibling.read_bytes() == b"keep-sibling"
    assert tables.calls


def test_xls_does_not_fallback_when_calamine_succeeds(tmp_path: Path) -> None:
    source = tmp_path / "legacy.xls"
    source.write_bytes(b"ole")
    derived = tmp_path / "legacy.xlsx"
    fallback = FakeXlsFallback(derived)
    extractor = FakeTabularExtractor(_extracted(source_file="legacy.xls"))
    uc, _tables, _objects = _uc(extractor, xls_fallback=fallback)

    result = uc.execute(_document(source, SignatureKind.OLE_SHEET))

    assert result.failed is False
    assert extractor.calls == [source]
    assert fallback.calls == []


def test_family_a_is_not_tabular_ingested() -> None:
    extractor = FakeTabularExtractor(_extracted())
    uc, tables, objects = _uc(extractor)

    result = uc.execute(_document(Path("claim.docx"), SignatureKind.OOXML_WORD))

    assert result.failed is True
    assert result.failure_reason is FailureReason.NARRATIVE_NOT_TABULAR
    assert extractor.calls == []
    assert tables.calls == []
    assert objects.bytes_objects == {}


def test_csv_prose_routed_document_is_not_extracted() -> None:
    extractor = FakeTabularExtractor(_extracted())
    uc, tables, _objects = _uc(extractor)
    document = Document.from_signature(
        Path("memo.csv"), FileSignature(SignatureKind.CSV, csv_column_count=1)
    )

    result = uc.execute(document)

    assert result.failed is True
    assert result.failure_reason is FailureReason.CSV_PROSE
    assert extractor.calls == []
    assert tables.calls == []


def test_skipped_sheets_are_profile_meta_only() -> None:
    path = Path("mixed.xlsx")
    data = _layer1()
    skipped = (
        _layer1(sheet_name="차트1", kind=SheetKind.CHART, columns=(), n_rows=0),
        _layer1(sheet_name="피벗", kind=SheetKind.PIVOT, columns=(), n_rows=0),
        _layer1(sheet_name="매크로", kind=SheetKind.MACRO, columns=(), n_rows=0),
        _layer1(sheet_name="빈시트", kind=SheetKind.EMPTY, columns=(), n_rows=0),
    )
    profiles = (
        _sheet_profile(),
        _sheet_profile(name="차트1", kind=SheetKind.CHART, columns=(), n_rows=0),
        _sheet_profile(name="피벗", kind=SheetKind.PIVOT, columns=(), n_rows=0),
        _sheet_profile(name="매크로", kind=SheetKind.MACRO, columns=(), n_rows=0),
        _sheet_profile(name="빈시트", kind=SheetKind.EMPTY, columns=(), n_rows=0),
    )
    extractor = FakeTabularExtractor(
        _extracted(
            sheets=(data, *skipped),
            profile_sheets=profiles,
        )
    )
    uc, _tables, objects = _uc(extractor)

    result = uc.execute(_document(path, SignatureKind.OOXML_SHEET))

    assert result.failed is False
    assert result.sheet_count == 1
    parquet_names = " ".join(result.parquet_keys)
    assert "차트1" not in parquet_names
    assert "피벗" not in parquet_names
    profile = objects.bytes_objects[result.profile_key or ""]
    assert b"chart" in profile
    assert b"pivot" in profile


def test_layer1_keeps_original_columns() -> None:
    original = ("품번", "원인", "대책")
    require_original_columns(original, original + ("source_file", "sheet_name"))
    with pytest.raises(TabularIngestError) as cause:
        require_original_columns(original, ("품번", "source_file"))
    assert cause.value.reason is FailureReason.CAUSE_COLUMN_DROPPED
    with pytest.raises(TabularIngestError) as generic:
        require_original_columns(("품번", "건수"), ("품번",))
    assert generic.value.reason is FailureReason.ORIGINAL_COLUMN_DROPPED


def test_excel_serial_dates_convert_from_1899_epoch() -> None:
    assert excel_serial_to_date(44927) == date(2023, 1, 1)
    assert convert_excel_serial(44927, column="발생일") == "2023-01-01"
    assert convert_excel_serial(3, column="건수") == 3


def test_fixed_width_padded_csv_extracts_quoted_columns(tmp_path: Path) -> None:
    from large_files_embedding.infrastructure.calamine_extractor import (
        CalamineTabularExtractor,
    )

    header = '"Org","Grant Number","City"'
    row = '"ACME, INC.","R01AI1","BOSTON"'
    width = 80
    lines = [
        " " * width,
        header + (" " * (width - len(header))),
        row + (" " * (width - len(row))),
    ]
    path = tmp_path / "nih-padded.csv"
    path.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
    extracted = CalamineTabularExtractor().extract(path, doc_id="nih")
    sheet = extracted.sheets[0]
    try:
        assert sheet.n_rows == 1
        assert "Grant Number" in sheet.original_columns
        assert "Org" in sheet.original_columns
        assert sheet.kind is SheetKind.DATA
    finally:
        if sheet.parquet_path is not None:
            sheet.parquet_path.unlink(missing_ok=True)


def test_infer_mapping_ledger_vs_unmapped() -> None:
    assert infer_fact_mapping(("품번", "원인", "대책", "건수")) == "claim_event"
    assert infer_fact_mapping(("품번", "근본원인", "대책")) == "claim_event"
    assert infer_fact_mapping(("차종", "클레임건수", "PPM")) == "monthly_quality_kpi"
    assert infer_fact_mapping(("컬럼A", "컬럼B")) is None
    assert map_fact_column("근본원인", "claim_event") == "cause"
    assert map_fact_column("대책", "claim_event") == "countermeasure"


def test_forbidden_engines_are_rejected() -> None:
    for engine in ("pandas", "xlrd", "openpyxl", "docling"):
        extracted = _extracted(engine=engine, fact_table=None, fact_rows=())
        with pytest.raises(TabularIngestError) as exc:
            validate_extracted_tabular(extracted)
        assert exc.value.reason is FailureReason.FORBIDDEN_ENGINE


def test_validate_keeps_cause_columns_on_valid_extract() -> None:
    validate_extracted_tabular(_extracted())


def test_mixed_ledger_and_kpi_sheets_insert_separately() -> None:
    path = Path("mixed.xlsx")
    kpi_columns = ("차종", "클레임건수", "PPM")
    extractor = FakeTabularExtractor(
        _extracted(
            sheets=(
                _layer1(sheet_name="원장"),
                _layer1(
                    sheet_name="월보",
                    columns=kpi_columns,
                    report_period="2024-03",
                    template_family="snapshot",
                    source_file="mixed.xlsx",
                ),
            ),
            profile_sheets=(
                _sheet_profile(),
                _sheet_profile(name="월보", columns=kpi_columns),
            ),
            fact_batches=(
                FactBatch(
                    table="claim_event",
                    grain=Grain.LEDGER,
                    report_period="2024-01",
                    rows=(
                        {
                            "source_file": "mixed.xlsx",
                            "sheet_name": "원장",
                            "cause": "누유",
                            "countermeasure": "가스켓 교체",
                        },
                    ),
                ),
                FactBatch(
                    table="monthly_quality_kpi",
                    grain=Grain.SNAPSHOT,
                    report_period="2024-03",
                    rows=(
                        {
                            "source_file": "mixed.xlsx",
                            "sheet_name": "월보",
                            "vehicle": "SUV",
                            "claim_count": 12,
                            "ppm": 3.5,
                        },
                    ),
                ),
            ),
            source_file="mixed.xlsx",
        )
    )
    uc, tables, objects = _uc(extractor)

    result = uc.execute(_document(path, SignatureKind.OOXML_SHEET))

    assert result.failed is False
    assert {call[0] for call in tables.calls} == {
        "claim_event",
        "monthly_quality_kpi",
    }
    claim_rows = next(call[1] for call in tables.calls if call[0] == "claim_event")
    kpi_rows = next(
        call[1] for call in tables.calls if call[0] == "monthly_quality_kpi"
    )
    assert "cause" in claim_rows[0]
    assert "countermeasure" in claim_rows[0]
    assert "cause" not in kpi_rows[0]
    assert objects.bytes_objects


def test_incomplete_claim_mapping_stays_layer1() -> None:
    path = Path("synonym.xlsx")
    columns = ("품번", "근본원인", "대책")
    extractor = FakeTabularExtractor(
        _extracted(
            sheets=(_layer1(columns=columns, source_file="synonym.xlsx"),),
            profile_sheets=(_sheet_profile(columns=columns),),
            fact_table="claim_event",
            fact_rows=(
                {
                    "source_file": "synonym.xlsx",
                    "sheet_name": "원장",
                    "part_no": "A-1",
                },
            ),
            source_file="synonym.xlsx",
        )
    )
    uc, tables, objects = _uc(extractor)

    result = uc.execute(_document(path, SignatureKind.OOXML_SHEET))

    assert result.failed is False
    assert result.failure_reason is None
    assert tables.calls == []
    assert result.parquet_keys
    assert any(key.endswith("profile.json") for key in objects.bytes_objects)
