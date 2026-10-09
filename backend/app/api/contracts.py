"""OpenAPI document including every contract schema, endpoint-backed or not.

Frontend TypeScript types are generated from this document (DECISIONS D-004).
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from pydantic import TypeAdapter
from pydantic.json_schema import models_json_schema

from app.api import studio
from app.core import audit
from app.core import schemas as core
from app.datasource import schemas as ds
from app.decision import schemas as dec
from app.equipment import schemas as eq
from app.feedback import schemas as fb
from app.monitoring import schemas as mon
from app.prediction import schemas as pred
from app.signals import schemas as sig

CONTRACT_MODELS = [
    core.LocalizedText,
    core.TimeWindow,
    core.ResultMeta,
    core.ApiError,
    ds.DataSourceConfig,
    ds.QueryParameter,
    ds.QueryTemplate,
    ds.RawTelemetryRow,
    ds.DeviceKeys,
    ds.SourceMetadata,
    ds.ColumnInfo,
    ds.TableInfo,
    ds.SourceSchema,
    ds.SqlTableLayout,
    ds.QueryTemplateSpec,
    ds.QueryTemplateAdminView,
    ds.QueryRunRequest,
    ds.QueryResult,
    audit.AuditEntry,
    sig.UnitConversion,
    sig.SignalDefinition,
    sig.SignalMapping,
    sig.SignalGroup,
    sig.VisualizationTemplate,
    sig.SignalConfigVersion,
    sig.NormalizedSample,
    sig.SeriesPoint,
    sig.VisualizationSeries,
    sig.SignalConfig,
    sig.SignalConfigVersionDetail,
    sig.SignalConfigState,
    sig.ChangeMeta,
    sig.SignalDefinitionChange,
    sig.SignalMappingChange,
    sig.SignalGroupChange,
    sig.VisualizationTemplateChange,
    sig.DeviceConfigChange,
    sig.PreviewRequest,
    sig.NormalizedSeries,
    sig.PreviewResponse,
    studio.ConnectionCheck,
    studio.LayoutColumn,
    studio.SourceLayout,
    studio.DeviceKey,
    studio.StudioDevice,
    studio.DeviceSuggestions,
    eq.Machine,
    eq.ComponentInstance,
    eq.ComponentLifecycle,
    eq.OperatingRegime,
    eq.MovementCycle,
    eq.MaintenanceEvent,
    eq.StateSegment,
    eq.FeatureStats,
    eq.KnownRegime,
    eq.RegimeCatalog,
    eq.FeatureValue,
    eq.RegimeAssignment,
    eq.CycleSummary,
    eq.MachineOperations,
    eq.LifecycleInstall,
    eq.UsageRecord,
    eq.ComponentAging,
    eq.MaintenanceEventCreate,
    eq.WorkflowTransition,
    eq.MaintenanceWorkflow,
    eq.WorkflowTransitionRequest,
    eq.MaintenanceRecordResult,
    eq.ImpactConfig,
    eq.RegimeComparison,
    eq.FeatureImpact,
    eq.MaintenanceImpact,
    mon.DataQualityReport,
    mon.FlaggedSpan,
    mon.AlignmentReport,
    mon.SignalPair,
    mon.QualityRequest,
    mon.QualityResponse,
    mon.FeatureDef,
    mon.FeatureSchema,
    mon.FeatureVector,
    mon.FeatureSkip,
    mon.FeatureExtraction,
    mon.FeatureStats,
    mon.Baseline,
    mon.BaselineVerification,
    mon.AdaptivePoint,
    mon.DegradationPoint,
    mon.DegradationSegment,
    mon.MaintenanceStep,
    mon.DegradationHistory,
    mon.RuleDefinition,
    mon.RuleSet,
    mon.RuleState,
    mon.RuleSetStatus,
    mon.RuleChange,
    mon.RuleHit,
    mon.WindowEvaluation,
    mon.AlarmAction,
    mon.AlarmEvaluationRequest,
    mon.AlarmEvaluationResult,
    pred.SamplingRequirement,
    pred.EligibilityCondition,
    pred.OperatorSpec,
    pred.AnomalyScoreResult,
    pred.ClassProbabilityResult,
    pred.DegradationIndicatorResult,
    pred.FailureProbabilityResult,
    pred.UnsupportedPrediction,
    dec.Evidence,
    dec.Decision,
    dec.Recommendation,
    dec.Alarm,
    fb.Feedback,
]

# Enums not reachable from any model above still need a generated type.
CONTRACT_ENUMS = [eq.OperatingState, eq.MaintenanceWorkflowState, eq.ImpactOutcome]


def build_openapi(app: FastAPI) -> dict[str, Any]:
    doc = app.openapi()
    ref = "#/components/schemas/{model}"
    _, defs = models_json_schema([(m, "serialization") for m in CONTRACT_MODELS], ref_template=ref)
    schemas = doc.setdefault("components", {}).setdefault("schemas", {})
    schemas.update(defs.get("$defs", {}))
    for enum in CONTRACT_ENUMS:
        schemas[enum.__name__] = TypeAdapter(enum).json_schema(ref_template=ref)
    union = TypeAdapter(pred.PredictionResult).json_schema(ref_template=ref, mode="serialization")
    union.pop("$defs", None)
    schemas["PredictionResult"] = union
    doc["components"]["schemas"] = dict(sorted(schemas.items()))
    return doc
