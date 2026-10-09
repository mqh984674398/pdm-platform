"""Shared contract primitives used by every layer (ARCHITECTURE §5)."""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class ContractModel(BaseModel):
    """Base for all contract schemas: unknown fields are rejected, instances are immutable."""

    model_config = ConfigDict(extra="forbid", frozen=True, json_schema_serialization_defaults_required=True)


class LocalizedText(ContractModel):
    """User-facing text in both supported languages (GEN-05)."""

    zh: str = Field(min_length=1)
    en: str = Field(min_length=1)


class TimeWindow(ContractModel):
    """Half-open interval [start, end) in timezone-aware timestamps."""

    start: AwareDatetime
    end: AwareDatetime

    @model_validator(mode="after")
    def _ordered(self) -> TimeWindow:
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class ResultMeta(ContractModel):
    """Provenance carried by every analytical result (GEN-06, GEN-03).

    Versions are opaque strings such as ``"ewma-torque@1.2.0"``. ``None`` is not allowed: a component
    that does not use a model still reports which rule or operator version produced the result.
    """

    model_version: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)
    config_version: str = Field(min_length=1)
    computed_at: AwareDatetime
    data_window: TimeWindow
    is_simulated: bool


class ApiError(ContractModel):
    code: str
    message: LocalizedText
    detail: dict[str, object] | None = None


T = TypeVar("T")


class Page(ContractModel, Generic[T]):
    items: list[T]
    total: int = Field(ge=0)
    offset: int = Field(ge=0)
    limit: int = Field(gt=0, le=1000)
