"""L1 adapter interface shared by the SQL adapter (T009) and the simulated adapter (T004)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from app.core.schemas import TimeWindow
from app.datasource.schemas import RawTelemetryRow, SourceMetadata, SourceSchema


class TimeSeriesAdapter(ABC):
    """Read-only access to raw telemetry. Implementations must never modify the source (L1-02)."""

    data_source_id: str
    is_simulated: bool

    @abstractmethod
    def discover(self) -> SourceMetadata:
        """List devices and key names available in the source."""

    @abstractmethod
    def inspect_schema(self) -> SourceSchema:
        """Describe tables and columns, read-only (L1-04)."""

    @abstractmethod
    def query_range(
        self, device_id: str, key_name: str, window: TimeWindow, limit: int
    ) -> list[RawTelemetryRow]:
        """Rows with ``window.start <= ts < window.end`` ordered by ts ascending, at most ``limit``."""

    @abstractmethod
    def query_incremental(
        self, device_id: str, key_name: str, since: datetime, limit: int
    ) -> list[RawTelemetryRow]:
        """Rows with ``ts > since`` ordered by ts ascending, at most ``limit`` (watermark reads, L1-03)."""
