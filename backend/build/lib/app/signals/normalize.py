"""Raw rows to normalized samples: engineering conversion and range flags (L2-02).

Normalization never drops, reorders, or resamples rows; quality analysis beyond the configured valid
range (gaps, jitter, duplicates…) is the quality service's job (T012).
"""

from __future__ import annotations

from collections.abc import Iterable

from app.datasource.schemas import RawTelemetryRow
from app.signals.schemas import (
    NormalizedSample,
    QualityFlag,
    SignalDefinition,
    UnitConversion,
)


def convert(value: float, conversion: UnitConversion | None) -> float:
    if conversion is None:
        return value
    return value * conversion.scale + conversion.offset


def normalize(
    rows: Iterable[RawTelemetryRow],
    signal: SignalDefinition,
    conversion: UnitConversion | None,
) -> list[NormalizedSample]:
    if conversion is not None and conversion.target_unit != signal.unit:
        raise ValueError(f"conversion targets '{conversion.target_unit}', signal unit is '{signal.unit}'")
    out = []
    for row in rows:
        flags: list[QualityFlag] = []
        value = None
        if row.value is None:
            flags.append(QualityFlag.MISSING)
        else:
            value = convert(row.value, conversion)
            low, high = signal.valid_min, signal.valid_max
            if (low is not None and value < low) or (high is not None and value > high):
                flags.append(QualityFlag.OUT_OF_RANGE)
        out.append(
            NormalizedSample(
                signal_id=signal.signal_id,
                ts=row.ts,
                value=value,
                unit=signal.unit,
                quality=flags,
                source_ref=row.source_ref,
                is_simulated=row.is_simulated,
            )
        )
    return out
