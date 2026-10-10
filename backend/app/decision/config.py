"""The decision configuration in force: rule set and aging policy from the deployment registry (T026).

Kind ``decision-config``. Without a champion in the registry the shipped defaults apply. The payload
holds the full rule set (thresholds included) and the aging policy, so a rollback restores both.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from sqlalchemy.orm import Session

from app.core.registry import DeploymentRegistry
from app.decision.aging import DEFAULT_POLICY, AgingPolicy
from app.monitoring.rules.definitions import DEFAULT_RULES
from app.monitoring.schemas import RuleSet

KIND = "decision-config"


@dataclass(frozen=True)
class DecisionConfig:
    rules: RuleSet
    policy: AgingPolicy
    version_id: str | None  # registry version, None for the shipped defaults

    def payload(self) -> dict:
        return {"rules": self.rules.model_dump(mode="json"), "policy": asdict(self.policy)}


def from_payload(payload: dict, version_id: str | None) -> DecisionConfig:
    return DecisionConfig(
        RuleSet.model_validate(payload["rules"]), AgingPolicy(**payload["policy"]), version_id
    )


DEFAULT = DecisionConfig(DEFAULT_RULES, DEFAULT_POLICY, None)


def active(session: Session) -> DecisionConfig:
    champ = DeploymentRegistry(session, KIND).champion()
    return from_payload(champ.payload, champ.version_id) if champ else DEFAULT
