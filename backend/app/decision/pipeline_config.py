# ruff: noqa: E501
"""Prediction configuration versions for one component (D-044).

An administrator drafts a configuration (relationships, decision pipeline, decision criteria, display),
then it is validated four ways (data, compile, historical replay, synthetic-scenario check), published as
an immutable version (content hash) and activated. Life cycle: DRAFT → VALIDATED → PUBLISHED, with at most
one ACTIVE version per component. Editing a draft clears its validation; a published version is never
changed, a new draft is cloned from it instead.

Scope of this phase: versions, validation, publishing and activation. The decision engine does not read
the criteria yet (phase 3), and ``compile`` knows the built-in algorithms only; a stage whose algorithm is
not implemented or whose prerequisites are not met is reported and never silently enabled.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import AwareDatetime, Field, field_validator
from sqlalchemy import JSON, Boolean, DateTime, Integer, String, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.core.audit import record as audit
from app.core.db import Base
from app.core.registry import DeploymentRegistry
from app.core.schemas import ContractModel, LocalizedText
from app.core.security import Principal, Role
from app.decision.schemas import EvidenceType
from app.equipment.lifecycle import EquipmentStore
from app.equipment.schemas import ComponentType
from app.signals.registry import SignalConfigStore
from app.signals.schemas import PhysicalQuantity as Q


def _t(zh: str, en: str) -> LocalizedText:
    return LocalizedText(zh=zh, en=en)


class PredictionConfigError(ValueError):
    pass


class PredictionConfigNotFoundError(KeyError):
    pass


class PredictionConfigPermissionError(PermissionError):
    pass


# --- content -----------------------------------------------------------------------------------------


class RelationType(StrEnum):
    INDEPENDENT = "INDEPENDENT"
    SHARED_DRIVETRAIN = "SHARED_DRIVETRAIN"
    MECHANICAL_DEPENDENCY = "MECHANICAL_DEPENDENCY"
    SHARED_SIGNAL = "SHARED_SIGNAL"


class Relationship(ContractModel):
    type: RelationType = RelationType.INDEPENDENT
    members: list[str] = Field(default_factory=list, description="Related component ids")
    affects_status_display: bool = False
    affects_common_cause: bool = False

    @field_validator("members")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("members must be unique")
        return v


class Stage(ContractModel):
    stage_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,40}$")
    algorithm: str
    enabled: bool = True
    params: dict[str, float | str | bool] = Field(default_factory=dict)


class Criteria(ContractModel):
    allowed_evidence_types: list[EvidenceType] = Field(
        default_factory=lambda: [
            EvidenceType.SAFETY, EvidenceType.STATISTICAL, EvidenceType.ANOMALY, EvidenceType.SUPERVISED
        ]
    )  # fmt: skip
    safety_first: bool = Field(default=True, description="Safety limits keep their minimum severity; fixed")
    model_max_severity: str = Field(default="WATCH", pattern=r"^(WATCH|WARNING)$")
    fusion: str = Field(default="SAFETY_FLOOR_RULES_MODELS", pattern=r"^SAFETY_FLOOR_RULES_MODELS$")
    confidence: str = Field(default="NONE", pattern=r"^(NONE|EVIDENCE_AGREEMENT)$")

    @field_validator("safety_first")
    @classmethod
    def _safety(cls, v: bool) -> bool:
        if not v:
            raise ValueError("the safety-first rule cannot be switched off")  # never weaken safety silently
        return v


class Display(ContractModel):
    own_status: bool = True
    related_status: bool = True
    trend: bool = True
    evidence: bool = True
    recommendations: bool = True
    alarms: bool = True


class ConfigContent(ContractModel):
    template_from: str | None = Field(default=None, description="Component whose configuration this copies")
    relationship: Relationship = Field(default_factory=Relationship)
    pipeline: list[Stage] = Field(default_factory=list)
    criteria: Criteria = Field(default_factory=Criteria)
    display: Display = Field(default_factory=Display)

    @field_validator("pipeline")
    @classmethod
    def _stage_ids(cls, v: list[Stage]) -> list[Stage]:
        ids = [s.stage_id for s in v]
        if len(set(ids)) != len(ids):
            raise ValueError("stage_id must be unique")
        return v


# --- algorithm catalog (built-ins; phase 3 adds the plugin interface) ------------------------------------


class AlgorithmSpec(ContractModel):
    algorithm_id: str
    category: str
    name: LocalizedText
    implemented: bool
    component_types: list[ComponentType] | None = None  # None = every type
    required_quantities: list[Q] = Field(default_factory=list)
    needs_validated_model: bool = False
    evidence_type: EvidenceType


_ALL_BUT = [ComponentType.BALL_SCREW, ComponentType.LINEAR_MOTOR, ComponentType.PNEUMATIC_CYLINDER,
            ComponentType.VACUUM_CUP]  # fmt: skip
CATALOG: dict[str, AlgorithmSpec] = {
    a.algorithm_id: a
    for a in [
        AlgorithmSpec(algorithm_id="engineering-rules", category="RULES", name=_t("工程规则", "Engineering rules"),
                      implemented=True, evidence_type=EvidenceType.SAFETY),
        AlgorithmSpec(algorithm_id="feature-engineering", category="FEATURES",
                      name=_t("特征工程", "Feature engineering"), implemented=True,
                      evidence_type=EvidenceType.STATISTICAL),
        AlgorithmSpec(algorithm_id="mahalanobis-t2", category="UNSUPERVISED",
                      name=_t("马氏距离 / Hotelling T²", "Mahalanobis / Hotelling T²"), implemented=False,
                      evidence_type=EvidenceType.ANOMALY),
        AlgorithmSpec(algorithm_id="decision-tree", category="ML", name=_t("决策树", "Decision tree"),
                      implemented=True, component_types=_ALL_BUT, needs_validated_model=True,
                      evidence_type=EvidenceType.SUPERVISED),
        AlgorithmSpec(algorithm_id="xgboost", category="ML", name=_t("XGBoost", "XGBoost"), implemented=True,
                      component_types=_ALL_BUT, needs_validated_model=True,
                      evidence_type=EvidenceType.SUPERVISED),
        AlgorithmSpec(algorithm_id="lstm", category="DL", name=_t("LSTM", "LSTM"), implemented=False,
                      component_types=_ALL_BUT, needs_validated_model=True,
                      evidence_type=EvidenceType.SUPERVISED),
        AlgorithmSpec(algorithm_id="drcnn", category="DL", name=_t("D-RCNN", "D-RCNN"), implemented=False,
                      component_types=_ALL_BUT, required_quantities=[Q.OTHER], needs_validated_model=True,
                      evidence_type=EvidenceType.SUPERVISED),
    ]
}  # fmt: skip


class Issue(ContractModel):
    level: str  # error | warning
    stage_id: str | None
    code: str
    message: LocalizedText


class CompiledStage(ContractModel):
    stage_id: str
    algorithm: str
    effective: bool = Field(description="Whether the stage will take part when the version is active")
    reason: LocalizedText | None = None


class CompileResult(ContractModel):
    ok: bool
    stages: list[CompiledStage]
    issues: list[Issue]


def compile_config(
    session: Session, component_id: str, content: ConfigContent
) -> tuple[CompileResult, ComponentType | None]:
    comp = next((c for c in EquipmentStore(session).components() if c.component_id == component_id), None)
    issues: list[Issue] = []
    if comp is None:
        return CompileResult(ok=False, stages=[], issues=[
            Issue(level="error", stage_id=None, code="UNKNOWN_COMPONENT",
                  message=_t("部件不存在", "Component does not exist"))
        ]), None  # fmt: skip
    cfg = SignalConfigStore(session).current().content
    defs = {s.signal_id: s for s in cfg.signals}
    have = {
        defs[m.signal_id].quantity
        for m in cfg.mappings
        if m.component_id == component_id and m.signal_id in defs
    }
    stages: list[CompiledStage] = []
    if not content.pipeline:
        issues.append(Issue(level="error", stage_id=None, code="EMPTY_PIPELINE",
                            message=_t("决策链路没有任何阶段", "The decision pipeline has no stage")))  # fmt: skip
    if not any(s.algorithm == "engineering-rules" and s.enabled for s in content.pipeline):
        issues.append(Issue(level="error", stage_id=None, code="NO_RULES",
                            message=_t("必须包含并启用工程规则（安全限值与核心判定）",
                                       "Engineering rules (safety limits, core decision) must be present and enabled")))  # fmt: skip
    for m in content.relationship.members:
        if m == component_id or not any(c.component_id == m for c in EquipmentStore(session).components()):
            issues.append(Issue(level="error", stage_id=None, code="BAD_RELATION_MEMBER",
                                message=_t(f"关联部件 {m} 无效", f"Related component {m} is not valid")))  # fmt: skip
    if content.relationship.type == RelationType.INDEPENDENT and content.relationship.members:
        issues.append(Issue(level="error", stage_id=None, code="INDEPENDENT_WITH_MEMBERS",
                            message=_t("独立监测不应列出关联部件", "Independent monitoring lists no related components")))  # fmt: skip
    for s in content.pipeline:
        spec = CATALOG.get(s.algorithm)
        why: LocalizedText | None = None
        if spec is None:
            issues.append(Issue(level="error", stage_id=s.stage_id, code="UNKNOWN_ALGORITHM",
                                message=_t(f"未知算法 {s.algorithm}", f"Unknown algorithm {s.algorithm}")))  # fmt: skip
        elif not s.enabled:
            why = _t("阶段已停用", "Stage is disabled")
        elif not spec.implemented:
            why = _t(f"{spec.name.zh} 尚无实现，只能保留接口，不参与判定",
                     f"{spec.name.en} has no implementation yet; kept as an interface only, not used")  # fmt: skip
            issues.append(Issue(level="warning", stage_id=s.stage_id, code="NOT_IMPLEMENTED", message=why))
        elif spec.component_types is not None and comp.type not in spec.component_types:
            why = _t(
                f"{spec.name.zh} 不适用于 {comp.type.value}",
                f"{spec.name.en} does not apply to {comp.type.value}",
            )
            issues.append(Issue(level="error", stage_id=s.stage_id, code="TYPE_NOT_SUPPORTED", message=why))
        else:
            missing = [q.value for q in spec.required_quantities if q not in have]
            if missing:
                why = _t(
                    f"缺少输入信号：{', '.join(missing)}", f"Missing input signals: {', '.join(missing)}"
                )
                issues.append(Issue(level="error", stage_id=s.stage_id, code="MISSING_INPUT", message=why))
            elif (
                spec.needs_validated_model
                and DeploymentRegistry(session, f"component-model:{comp.type.value}").champion() is None
            ):
                why = _t(f"{spec.name.zh} 需要已验证并部署的模型，当前没有；不参与判定",
                         f"{spec.name.en} needs a validated, deployed model; none exists, so it takes no part")  # fmt: skip
                issues.append(
                    Issue(level="warning", stage_id=s.stage_id, code="NO_VALIDATED_MODEL", message=why)
                )
            if spec.evidence_type not in content.criteria.allowed_evidence_types and why is None:
                why = _t(
                    "判定标准不允许该类证据参与", "The decision criteria do not allow this evidence type"
                )
                issues.append(
                    Issue(level="warning", stage_id=s.stage_id, code="EVIDENCE_NOT_ALLOWED", message=why)
                )
        stages.append(
            CompiledStage(stage_id=s.stage_id, algorithm=s.algorithm, effective=why is None, reason=why)
        )
    ok = not any(i.level == "error" for i in issues)
    return CompileResult(ok=ok, stages=stages, issues=issues), comp.type


# --- storage -------------------------------------------------------------------------------------------


class ConfigStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    PUBLISHED = "PUBLISHED"


class CheckResult(ContractModel):
    name: str  # data | compile | replay | simulation
    ok: bool
    summary: LocalizedText
    details: dict[str, Any] = Field(default_factory=dict)


class PredictionConfig(ContractModel):
    config_id: str
    component_id: str
    version: int
    status: ConfigStatus
    active: bool
    content: ConfigContent
    content_hash: str
    validation: list[CheckResult]
    created_by: str
    created_at: AwareDatetime
    published_by: str | None = None
    published_at: AwareDatetime | None = None
    publish_comment: str = ""


class ConfigRecord(Base):
    __tablename__ = "prediction_configs"

    config_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    component_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    validation: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_by: Mapped[str | None] = mapped_column(String(64))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    publish_comment: Mapped[str] = mapped_column(String(2000), nullable=False, default="")

    def to_model(self) -> PredictionConfig:
        def aware(t: datetime | None) -> datetime | None:
            return t if t is None or t.tzinfo else t.replace(tzinfo=UTC)

        return PredictionConfig(
            config_id=self.config_id, component_id=self.component_id, version=self.version,
            status=ConfigStatus(self.status), active=self.active,
            content=ConfigContent.model_validate(self.content), content_hash=self.content_hash,
            validation=[CheckResult.model_validate(c) for c in self.validation],
            created_by=self.created_by, created_at=aware(self.created_at),
            published_by=self.published_by, published_at=aware(self.published_at),
            publish_comment=self.publish_comment,
        )  # fmt: skip


def content_hash(content: ConfigContent) -> str:
    return hashlib.sha256(
        json.dumps(content.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _admin(who: Principal) -> None:
    if who.role != Role.ADMIN:
        raise PredictionConfigPermissionError("only an administrator manages prediction configurations")


class PredictionConfigStore:
    def __init__(self, session: Session):
        self.session = session

    def _row(self, config_id: str) -> ConfigRecord:
        rec = self.session.get(ConfigRecord, config_id)
        if rec is None:
            raise PredictionConfigNotFoundError(config_id)
        return rec

    def get(self, config_id: str) -> PredictionConfig:
        return self._row(config_id).to_model()

    def versions(self, component_id: str) -> list[PredictionConfig]:
        stmt = (
            select(ConfigRecord)
            .where(ConfigRecord.component_id == component_id)
            .order_by(ConfigRecord.version)
        )
        return [r.to_model() for r in self.session.scalars(stmt)]

    def active(self, component_id: str) -> PredictionConfig | None:
        stmt = select(ConfigRecord).where(
            ConfigRecord.component_id == component_id, ConfigRecord.active.is_(True)
        )
        rec = self.session.scalar(stmt)
        return rec.to_model() if rec else None

    def create_draft(self, component_id: str, content: ConfigContent, who: Principal) -> PredictionConfig:
        _admin(who)
        if not any(c.component_id == component_id for c in EquipmentStore(self.session).components()):
            raise PredictionConfigNotFoundError(component_id)
        n = max((v.version for v in self.versions(component_id)), default=0) + 1
        rec = ConfigRecord(
            config_id=f"{component_id}@v{n}", component_id=component_id, version=n,
            status=ConfigStatus.DRAFT.value, active=False, content=content.model_dump(mode="json"),
            content_hash=content_hash(content), validation=[], created_by=who.user_id,
            created_at=datetime.now(UTC),
        )  # fmt: skip
        self.session.add(rec)
        audit(self.session, who, "predcfg.create", "prediction_config", rec.config_id)
        self.session.flush()
        return rec.to_model()

    def update_draft(self, config_id: str, content: ConfigContent, who: Principal) -> PredictionConfig:
        _admin(who)
        rec = self._row(config_id)
        if rec.status == ConfigStatus.PUBLISHED.value:
            raise PredictionConfigError("a published version is immutable; create a new draft from it")
        rec.content, rec.content_hash = content.model_dump(mode="json"), content_hash(content)
        rec.status, rec.validation = ConfigStatus.DRAFT.value, []  # any edit voids earlier validation
        audit(self.session, who, "predcfg.update", "prediction_config", config_id)
        self.session.flush()
        return rec.to_model()

    def clone(self, config_id: str, who: Principal) -> PredictionConfig:
        src = self.get(config_id)
        return self.create_draft(src.component_id, src.content, who)

    def delete_draft(self, config_id: str, who: Principal) -> None:
        _admin(who)
        rec = self._row(config_id)
        if rec.status == ConfigStatus.PUBLISHED.value:
            raise PredictionConfigError("a published version cannot be deleted")
        audit(self.session, who, "predcfg.delete", "prediction_config", config_id)
        self.session.delete(rec)
        self.session.flush()

    def save_validation(self, config_id: str, checks: list[CheckResult], who: Principal) -> PredictionConfig:
        _admin(who)
        rec = self._row(config_id)
        if rec.status == ConfigStatus.PUBLISHED.value:
            raise PredictionConfigError("a published version is already validated and immutable")
        rec.validation = [c.model_dump(mode="json") for c in checks]
        rec.status = (ConfigStatus.VALIDATED if all(c.ok for c in checks) and len(checks) == 4
                      else ConfigStatus.DRAFT).value  # fmt: skip
        audit(self.session, who, "predcfg.validate", "prediction_config", config_id,
              ok=rec.status == ConfigStatus.VALIDATED.value, hash=rec.content_hash)  # fmt: skip
        self.session.flush()
        return rec.to_model()

    def publish(self, config_id: str, who: Principal, comment: str) -> PredictionConfig:
        _admin(who)
        rec = self._row(config_id)
        if rec.status != ConfigStatus.VALIDATED.value:
            raise PredictionConfigError(
                "only a version that passed all four validation checks can be published"
            )
        if not comment.strip():
            raise PredictionConfigError("a comment is required")
        if rec.content_hash != content_hash(ConfigContent.model_validate(rec.content)):
            raise PredictionConfigError("the content changed after validation")
        rec.status, rec.published_by = ConfigStatus.PUBLISHED.value, who.user_id
        rec.published_at, rec.publish_comment = datetime.now(UTC), comment.strip()
        audit(self.session, who, "predcfg.publish", "prediction_config", config_id, hash=rec.content_hash,
              comment=comment.strip())  # fmt: skip
        self.session.flush()
        return rec.to_model()

    def activate(self, config_id: str, who: Principal) -> PredictionConfig:
        _admin(who)
        rec = self._row(config_id)
        if rec.status != ConfigStatus.PUBLISHED.value:
            raise PredictionConfigError("only a published version can be activated")
        for other in self.session.scalars(
            select(ConfigRecord).where(
                ConfigRecord.component_id == rec.component_id, ConfigRecord.active.is_(True)
            )
        ):
            other.active = False
        rec.active = True
        audit(self.session, who, "predcfg.activate", "prediction_config", config_id, hash=rec.content_hash)
        self.session.flush()
        return rec.to_model()

    def deactivate(self, component_id: str, who: Principal) -> None:
        _admin(who)
        cur = self.active(component_id)
        if cur is None:
            raise PredictionConfigNotFoundError(component_id)
        self._row(cur.config_id).active = False
        audit(self.session, who, "predcfg.deactivate", "prediction_config", cur.config_id)
        self.session.flush()
