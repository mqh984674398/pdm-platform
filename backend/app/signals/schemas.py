"""L2 contracts: signal registry, mappings, units, groups, visualization, versions."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field

from app.core.schemas import ContractModel, LocalizedText


class PhysicalQuantity(StrEnum):
    SPEED = "SPEED"
    TORQUE = "TORQUE"
    DURATION = "DURATION"
    POSITION = "POSITION"
    CURRENT = "CURRENT"
    PRESSURE = "PRESSURE"
    OTHER = "OTHER"


class UnitConversion(ContractModel):
    """Linear conversion ``target = source * scale + offset`` (L2-02)."""

    source_unit: str
    target_unit: str
    scale: float = 1.0
    offset: float = 0.0


class SignalDefinition(ContractModel):
    signal_id: str
    name: LocalizedText
    quantity: PhysicalQuantity
    unit: str = Field(description="Engineering unit of normalized values, e.g. 'rpm', 'N*m', 's'")
    expected_sampling_s: float | None = Field(default=None, gt=0)
    valid_min: float | None = None
    valid_max: float | None = None


class SignalMapping(ContractModel):
    """Binds a logical signal to a device + KeyName in a data source (L2-01)."""

    signal_id: str
    data_source_id: str
    template_id: str
    device_id: str
    key_name: str
    time_field: str
    value_field: str
    conversion: UnitConversion | None = None
    component_id: str | None = None


class SignalGroup(ContractModel):
    group_id: str
    name: LocalizedText
    signal_ids: list[str] = Field(min_length=1)
    component_id: str | None = None


class ChartKind(StrEnum):
    LINE = "LINE"
    SCATTER = "SCATTER"
    HISTOGRAM = "HISTOGRAM"
    CYCLE_DURATION = "CYCLE_DURATION"


class VisualizationTemplate(ContractModel):
    template_id: str
    name: LocalizedText
    chart: ChartKind
    signal_ids: list[str] = Field(min_length=1)
    y_min: float | None = None
    y_max: float | None = None


class SignalConfigVersion(ContractModel):
    """Immutable snapshot reference for the signal configuration (L2-05)."""

    version: int = Field(ge=1)
    created_at: AwareDatetime
    created_by: str
    comment: str = ""
    content_hash: str


class QualityFlag(StrEnum):
    MISSING = "MISSING"
    DUPLICATE = "DUPLICATE"
    OUT_OF_ORDER = "OUT_OF_ORDER"
    JITTER = "JITTER"
    GAP = "GAP"
    OUT_OF_RANGE = "OUT_OF_RANGE"
    UNIT_SUSPECT = "UNIT_SUSPECT"
    MISALIGNED = "MISALIGNED"


class NormalizedSample(ContractModel):
    """Full-resolution normalized signal value (ARCHITECTURE §4 layer 2)."""

    signal_id: str
    ts: AwareDatetime
    value: float | None
    unit: str
    quality: list[QualityFlag] = Field(default_factory=list)
    source_ref: str
    is_simulated: bool


class SeriesPoint(ContractModel):
    ts: AwareDatetime
    value: float | None


class VisualizationSeries(ContractModel):
    """Downsampled data for charts only; never an algorithm input (L2-06)."""

    signal_id: str
    unit: str
    points: list[SeriesPoint]
    downsampled: bool
    source_point_count: int = Field(ge=0)
    method: str | None = Field(default=None, description="e.g. 'lttb'")
    is_simulated: bool
