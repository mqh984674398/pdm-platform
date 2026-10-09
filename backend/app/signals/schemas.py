"""L2 contracts: signal registry, mappings, units, groups, visualization, versions."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field, model_validator

from app.core.schemas import ContractModel, LocalizedText, TimeWindow


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
    BIAS_SUSPECT = "BIAS_SUSPECT"


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


# --- configuration content, changes, and preview (T011) -----------------------------------------


def _duplicates(values: list) -> list:
    seen, dup = set(), []
    for v in values:
        if v in seen and v not in dup:
            dup.append(v)
        seen.add(v)
    return dup


class SignalConfig(ContractModel):
    """The whole signal configuration; each saved state is one immutable version (L2-05).

    Invariants: ids are unique; every mapping, group, and chart refers to a defined signal; a signal
    has at most one mapping and a device key feeds at most one signal; a conversion's target unit is
    the signal's unit.
    """

    signals: list[SignalDefinition] = Field(default_factory=list)
    mappings: list[SignalMapping] = Field(default_factory=list)
    groups: list[SignalGroup] = Field(default_factory=list)
    visualizations: list[VisualizationTemplate] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> SignalConfig:
        problems: list[str] = []
        units = {s.signal_id: s.unit for s in self.signals}
        checks = [
            ("signal", [s.signal_id for s in self.signals]),
            ("mapping for signal", [m.signal_id for m in self.mappings]),
            ("device key", [f"{m.data_source_id}/{m.device_id}/{m.key_name}" for m in self.mappings]),
            ("group", [g.group_id for g in self.groups]),
            ("chart template", [v.template_id for v in self.visualizations]),
        ]
        for what, ids in checks:
            problems += [f"duplicate {what} '{d}'" for d in _duplicates(ids)]
        for m in self.mappings:
            if m.signal_id not in units:
                problems.append(f"mapping refers to undefined signal '{m.signal_id}'")
            elif m.conversion and m.conversion.target_unit != units[m.signal_id]:
                problems.append(
                    f"mapping for '{m.signal_id}' converts to '{m.conversion.target_unit}', "
                    f"but the signal's unit is '{units[m.signal_id]}'"
                )
        for kind, items in (("group", self.groups), ("chart template", self.visualizations)):
            for item in items:
                item_id = getattr(item, "group_id", None) or getattr(item, "template_id", "")
                problems += [
                    f"{kind} '{item_id}' refers to undefined signal '{sid}'"
                    for sid in item.signal_ids
                    if sid not in units
                ]
        if problems:
            raise ValueError("; ".join(problems))
        return self


class SignalConfigVersionDetail(SignalConfigVersion):
    content: SignalConfig


class SignalConfigState(ContractModel):
    """Current configuration; ``version`` is None until the first save."""

    version: SignalConfigVersion | None
    content: SignalConfig


class ChangeMeta(ContractModel):
    comment: str = Field(default="", max_length=500)
    base_version: int | None = Field(
        default=None,
        ge=0,
        description="Reject the change unless this is still the current version (0 = none yet)",
    )


class SignalDefinitionChange(ChangeMeta):
    item: SignalDefinition


class SignalMappingChange(ChangeMeta):
    item: SignalMapping


class SignalGroupChange(ChangeMeta):
    item: SignalGroup


class VisualizationTemplateChange(ChangeMeta):
    item: VisualizationTemplate


class DeviceConfigChange(ChangeMeta):
    """Replaces everything configured for one device of one source (the Studio's save)."""

    signals: list[SignalDefinition] = Field(min_length=1)
    mappings: list[SignalMapping] = Field(min_length=1)
    groups: list[SignalGroup] = Field(default_factory=list)
    visualizations: list[VisualizationTemplate] = Field(default_factory=list)


class PreviewRequest(ContractModel):
    """Preview mapped signals over a window. Definitions not given here come from the current
    configuration, so drafts can be previewed before they are saved."""

    mappings: list[SignalMapping] = Field(min_length=1, max_length=32)
    signals: list[SignalDefinition] = Field(default_factory=list)
    window: TimeWindow
    max_points: int = Field(default=1000, ge=10, le=10_000)
    include_normalized: bool = True


class NormalizedSeries(ContractModel):
    """Full-resolution normalized values (algorithm input), never downsampled (L2-06)."""

    signal_id: str
    unit: str
    samples: list[NormalizedSample]
    truncated: bool = Field(description="True when the source returned more rows than the preview limit")


class PreviewResponse(ContractModel):
    window: TimeWindow
    normalized: list[NormalizedSeries]
    visualization: list[VisualizationSeries]
    is_simulated: bool
