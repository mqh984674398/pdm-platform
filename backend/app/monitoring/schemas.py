"""L4 contracts: data quality, features, baselines."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field, model_validator

from app.core.schemas import ContractModel, LocalizedText, ResultMeta, TimeWindow
from app.signals.schemas import QualityFlag, SignalDefinition, SignalMapping


class FlaggedSpan(ContractModel):
    """A stretch of the analysed window with quality findings: an observation window or a gap."""

    start: AwareDatetime
    end: AwareDatetime
    flags: list[QualityFlag]


class DataQualityReport(ContractModel):
    """Quality of one signal over a window, computed on full-resolution rows (L4-01, L2-06).

    Problems are reported, never corrected: values stay as delivered. Checks that cannot be evaluated
    for this signal or source are listed in ``not_evaluated`` instead of being reported as clean.
    """

    signal_id: str
    window: TimeWindow
    sample_count: int = Field(ge=0)
    missing_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    out_of_order_count: int = Field(ge=0)
    gap_count: int = Field(ge=0)
    median_interval_s: float | None = Field(default=None, ge=0)
    interval_jitter_s: float | None = Field(default=None, ge=0)
    unit_suspect: bool = False
    is_simulated: bool
    flags: list[QualityFlag] = Field(default_factory=list)
    expected_interval_s: float | None = Field(default=None, gt=0)
    observation_window_count: int = Field(default=0, ge=0)
    largest_gap_s: float | None = Field(default=None, ge=0)
    gap_threshold_s: float | None = Field(default=None, gt=0)
    out_of_range_count: int = Field(default=0, ge=0)
    valid_range: tuple[float | None, float | None] | None = Field(
        default=None, description="Range used for OUT_OF_RANGE: the signal's own, else a unit default"
    )
    not_evaluated: list[QualityFlag] = Field(default_factory=list)
    spans: list[FlaggedSpan] = Field(default_factory=list)


class AlignmentReport(ContractModel):
    """Speed/torque consistency (L4-02): timestamp pairing within a tolerance, motion agreement per
    observation window, and the torque level at standstill compared with its recent reference."""

    speed_signal_id: str
    torque_signal_id: str
    window: TimeWindow
    tolerance_s: float = Field(gt=0)
    paired_count: int = Field(ge=0)
    unpaired_speed_count: int = Field(ge=0)
    unpaired_torque_count: int = Field(ge=0)
    median_time_offset_s: float | None = Field(default=None, ge=0)
    evaluated_windows: int = Field(ge=0)
    agreement: float | None = Field(
        default=None, ge=0, le=1, description="Lowest per-window motion agreement"
    )
    min_agreement: float = Field(ge=0, le=1, description="Windows below this are MISALIGNED")
    misaligned_windows: list[TimeWindow] = Field(default_factory=list)
    standstill_torque: float | None = None
    reference_standstill_torque: float | None = None
    flags: list[QualityFlag] = Field(default_factory=list)
    not_evaluated: list[QualityFlag] = Field(default_factory=list)
    is_simulated: bool


class SignalPair(ContractModel):
    speed_signal_id: str
    torque_signal_id: str


class QualityRequest(ContractModel):
    """Assess saved signals (``signal_ids``) and/or drafts (``mappings`` + ``signals``) over a window.

    The lookback period before the window is read only as a reference for level checks (unit scale,
    standstill bias) and gap spacing. Speed/torque pairs default to signals of the same component.
    """

    signal_ids: list[str] = Field(default_factory=list, max_length=32)
    mappings: list[SignalMapping] = Field(default_factory=list, max_length=32)
    signals: list[SignalDefinition] = Field(default_factory=list)
    window: TimeWindow
    lookback_hours: float = Field(default=168, ge=0, le=336)
    pairs: list[SignalPair] | None = None
    tolerance_s: float | None = Field(default=None, gt=0, le=60)


class QualityResponse(ContractModel):
    window: TimeWindow
    reports: list[DataQualityReport]
    alignment: list[AlignmentReport]
    is_simulated: bool


class FeatureDef(ContractModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    unit: str
    description: LocalizedText
    residual: bool = Field(
        default=False, description="Condition-normalized residual against the matched regime (L4-03)"
    )


class FeatureSchema(ContractModel):
    """Declared, versioned feature set (L4-04). ``ref`` is ``feature_set@version``.

    A published version is immutable: changing a definition needs a new version."""

    feature_set: str
    version: str
    component_type: str
    features: list[FeatureDef] = Field(min_length=1)

    @property
    def ref(self) -> str:
        return f"{self.feature_set}@{self.version}"


class FeatureVector(ContractModel):
    """Features of one component over one closed observation window, computed from that window only.

    ``None`` means not computable in this window (signal absent, too few operations, or a residual
    without a matched regime); it is never filled in."""

    component_id: str
    lifecycle_id: str
    regime_id: str | None
    regime_status: str = Field(description="KNOWN, UNSUPPORTED or NOT_EVALUATED")
    catalog_id: str | None = Field(description="Regime catalog used for the residuals")
    feature_ref: str = Field(description="feature_set@version")
    window: TimeWindow
    source_signals: list[str]
    values: dict[str, float | None]
    is_simulated: bool


class FeatureSkip(ContractModel):
    """A running window for which a component got no feature vector, and why."""

    component_id: str
    window: TimeWindow
    reason: LocalizedText


class FeatureExtraction(ContractModel):
    vectors: list[FeatureVector]
    skipped: list[FeatureSkip]
    not_supported: list[str] = Field(description="Components whose type has no feature set (template only)")
    is_simulated: bool


class BaselineKind(StrEnum):
    """Three independent baselines (L4-05)."""

    VERIFIED_HEALTHY = "VERIFIED_HEALTHY"
    ADAPTIVE = "ADAPTIVE"
    DEGRADATION_HISTORY = "DEGRADATION_HISTORY"


class FeatureStats(ContractModel):
    mean: float
    std: float = Field(ge=0)
    p05: float | None = None
    p50: float | None = None
    p95: float | None = None
    n: int = Field(ge=0)


class Baseline(ContractModel):
    baseline_id: str
    kind: BaselineKind
    component_id: str
    lifecycle_id: str
    regime_id: str | None
    feature_ref: str
    window: TimeWindow
    stats: dict[str, FeatureStats]
    verified_by: str | None = None
    verified_at: AwareDatetime | None = None
    meta: ResultMeta

    @model_validator(mode="after")
    def _verification(self) -> Baseline:
        # Normal aging must never be absorbed silently into the healthy reference (L4-06):
        # a verified-healthy baseline exists only through an explicit, attributed verification.
        verified = self.verified_by is not None and self.verified_at is not None
        if self.kind == BaselineKind.VERIFIED_HEALTHY and not verified:
            raise ValueError("VERIFIED_HEALTHY baseline requires verified_by and verified_at")
        if self.kind != BaselineKind.VERIFIED_HEALTHY and (self.verified_by or self.verified_at):
            raise ValueError("only VERIFIED_HEALTHY baselines carry verification fields")
        return self
