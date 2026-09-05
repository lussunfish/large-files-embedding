"""Route an ingest path to a document family without stopping the batch."""

from collections.abc import Sequence
from pathlib import Path

from large_files_embedding.domain.document import (
    Document,
    FileSignature,
    FormatDetector,
    SignatureKind,
)


class RouteFile:
    def __init__(self, detector: FormatDetector) -> None:
        self._detector = detector
        self.failure_queue: list[Document] = []

    def execute(self, path: Path) -> Document:
        try:
            signature = self._detector.detect(path)
        except OSError:
            signature = FileSignature(SignatureKind.UNKNOWN)
        document = Document.from_signature(path, signature)
        if document.queued_for_failure:
            self.failure_queue.append(document)
        return document

    def execute_many(self, paths: Sequence[Path]) -> list[Document]:
        return [self.execute(path) for path in paths]
