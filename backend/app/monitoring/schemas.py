"""L4 contracts: data quality, features, baselines."""

from __future__ import annotations

from enum import StrEnum

from pydantic import AwareDatetime, Field, model_validator

from app.core.schemas import ContractModel, LocalizedText, ResultMeta, TimeWindow


class DataQualityReport(ContractModel):
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


class FeatureDef(ContractModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    unit: str
    description: LocalizedText


class FeatureSchema(ContractModel):
    """Declared, versioned feature set (L4-04). ``ref`` is ``feature_set@version``."""

    feature_set: str
    version: str
    features: list[FeatureDef] = Field(min_length=1)

    @property
    def ref(self) -> str:
        return f"{self.feature_set}@{self.version}"


class FeatureVector(ContractModel):
    component_id: str
    lifecycle_id: str
    regime_id: str | None
    feature_ref: str = Field(description="feature_set@version")
    window: TimeWindow
    values: dict[str, float | None]
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
