"""Map domain errors to ApiError responses with bilingual messages (GEN-05).

Database driver messages are never returned: they can echo SQL text or connection details.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm.exc import StaleDataError

from app.api.studio import UnknownDeviceError
from app.core.registry import RegistryError, RegistryNotFoundError, RegistryPermissionError
from app.core.schemas import ApiError, LocalizedText
from app.datasource.query_service.registry import TemplateConflictError, TemplateNotFoundError
from app.datasource.query_service.service import ParameterError
from app.datasource.query_service.sources import UnknownSourceError
from app.datasource.query_service.sql_guard import TemplateSqlError
from app.datasource.sql import AdapterError, BusyError, LayoutError, QueryLimitError
from app.equipment.lifecycle import EquipmentConflictError, EquipmentNotFoundError
from app.equipment.maintenance import WorkflowPermissionError, WorkflowTransitionError
from app.feedback.service import FeedbackNotFoundError, FeedbackPermissionError
from app.llm.assistant import AssistantDisabled, AssistantResponseError
from app.llm.client import LlmCancelled, LlmTimeout, LlmUnavailable
from app.llm.endpoint import EndpointRejected, ModelRejected
from app.llm.rag import DocumentError, DocumentNotFoundError, DocumentPermissionError
from app.llm.settings import LlmPermissionError
from app.monitoring.alarms.service import AlarmNotFoundError, AlarmTransitionError
from app.monitoring.baselines.verified import BaselineError, BaselinePermissionError
from app.monitoring.features.store import FeatureConflictError
from app.monitoring.quality.service import QualityRequestError, UnknownQualitySignalError
from app.monitoring.rules.settings import RuleNotFoundError, RulePermissionError
from app.optimization.candidates import SafetyChangeError
from app.optimization.service import NoRunError, NoSuiteError
from app.prediction.models.registry import ModelRegistryError
from app.signals.preview import PreviewError, UnknownSignalError
from app.signals.registry import ConfigConflictError, ConfigNotFoundError

log = logging.getLogger("pdm.api")

# exception type -> (HTTP status, code, zh, en); first match wins
ERRORS: list[tuple[type[Exception], int, str, str, str]] = [
    (UnknownDeviceError, 404, "unknown_device", "数据源中没有该设备。", "Device not found in this data source."),
    (UnknownSignalError, 404, "unknown_signal", "未找到该信号。", "Signal not found."),
    (ConfigNotFoundError, 404, "unknown_config_item", "未找到该配置项或版本。", "Configuration item or version not found."),
    (ConfigConflictError, 409, "config_conflict", "信号配置冲突，未保存。", "Signal configuration conflict; nothing was saved."),
    (UnknownQualitySignalError, 404, "unknown_signal", "未找到该信号。", "Signal not found."),
    (QualityRequestError, 422, "invalid_quality_request", "质量检查请求无效。", "The quality request is invalid."),
    (PreviewError, 422, "invalid_preview", "预览请求无效。", "The preview request is invalid."),
    (EquipmentNotFoundError, 404, "unknown_equipment", "未找到该设备、部件、生命周期或工作流。", "Machine, component, lifecycle or workflow not found."),
    (EquipmentConflictError, 409, "equipment_conflict", "与已记录的设备或维护历史冲突，未保存。", "Conflicts with the recorded equipment or maintenance history; nothing was saved."),
    (WorkflowTransitionError, 409, "workflow_transition_refused", "不允许该维护工作流状态转换。", "This maintenance workflow transition is not allowed."),
    (WorkflowPermissionError, 403, "workflow_review_role", "关闭复核需要工程师角色。", "Closing a review requires the engineer role."),
    (AlarmNotFoundError, 404, "unknown_alarm", "未找到该报警。", "Alarm not found."),
    (AlarmTransitionError, 409, "alarm_transition_refused", "不允许该报警状态变更。", "This alarm status change is not allowed."),
    (RuleNotFoundError, 404, "unknown_rule", "规则集中没有该规则。", "Rule not found in the rule set."),
    (RulePermissionError, 403, "rule_change_role", "安全规则只能由管理员启用或停用。", "Only an administrator can enable or disable a safety rule."),
    (BaselinePermissionError, 403, "baseline_verify_role", "确认健康基准需要工程师角色。", "Verifying a healthy reference requires the engineer role."),
    (BaselineError, 422, "baseline_refused", "无法建立该基准，未保存。", "The baseline could not be created; nothing was saved."),
    (FeatureConflictError, 409, "feature_conflict", "与已发布的特征版本或已存储的特征冲突。", "Conflicts with a published feature version or stored features."),
    (StaleDataError, 409, "concurrent_change", "记录已被他人修改，请刷新后重试。", "The record was changed by someone else. Reload and retry."),
    (EndpointRejected, 422, "llm_endpoint_rejected", "只允许本机或局域网内的 Ollama 地址，已拒绝远程/云端地址。", "Only a local or LAN Ollama endpoint is allowed; remote or cloud endpoints are refused."),
    (ModelRejected, 422, "llm_model_rejected", "该模型不允许使用（云端路由、未安装或不在允许列表中）。", "This model is not allowed (cloud-routed, not installed, or not on the allowlist)."),
    (LlmPermissionError, 403, "llm_settings_role", "修改 Ollama 设置需要管理员角色。", "Changing the Ollama settings requires the administrator role."),
    (AssistantDisabled, 503, "assistant_disabled", "助手未启用或未选择模型；平台其他功能不受影响。", "The assistant is off or has no model; the rest of the platform is unaffected."),
    (LlmTimeout, 504, "llm_timeout", "本地模型响应超时。", "The local model did not answer in time."),
    (LlmCancelled, 499, "llm_cancelled", "已取消。", "Cancelled."),
    (LlmUnavailable, 503, "llm_unavailable", "无法连接本地 Ollama；监测和报警不受影响。", "The local Ollama cannot be reached; monitoring and alarms are unaffected."),
    (AssistantResponseError, 502, "llm_bad_answer", "模型回答格式不符合要求，已丢弃。", "The model's answer did not have the required structure and was discarded."),
    (DocumentPermissionError, 403, "document_role", "添加文档需要工程师角色，批准需要管理员角色。", "Adding a document requires the engineer role; approving requires the administrator role."),
    (DocumentNotFoundError, 404, "unknown_document", "未找到该文档。", "Document not found."),
    (DocumentError, 422, "document_refused", "无法处理该文档。", "The document could not be processed."),
    (FeedbackPermissionError, 403, "feedback_role", "提交反馈需要维护角色，复核需要工程师角色。", "Feedback requires the maintenance role; review requires the engineer role."),
    (FeedbackNotFoundError, 404, "unknown_feedback", "未找到该反馈。", "Feedback not found."),
    (RegistryNotFoundError, 404, "unknown_version", "未找到该版本。", "Version not found."),
    (RegistryPermissionError, 403, "registry_role", "晋升需要管理员角色；提交、拒绝和回滚需要工程师角色。", "Promotion requires the administrator role; proposing, rejecting and rolling back require the engineer role."),
    (RegistryError, 409, "registry_refused", "注册表拒绝了该操作，未保存。", "The registry refused this action; nothing was saved."),
    (ModelRegistryError, 404, "unknown_model", "未找到该模型或其文件校验失败。", "Model not found or its file failed verification."),
    (NoSuiteError, 409, "no_regression_suite", "没有可用于回放评估的回归用例（Golden Case）。", "No regression suite (Golden Cases) is available for replay."),
    (NoRunError, 404, "no_optimization_run", "还没有参数优化运行。", "No optimization run yet."),
    (SafetyChangeError, 422, "safety_rule_change", "候选配置修改了安全规则，已拒绝。", "The candidate changes a safety rule and was refused."),
    (UnknownSourceError, 404, "unknown_source", "未找到该数据源。", "Data source not found."),
    (TemplateNotFoundError, 404, "unknown_template", "未找到该查询模板。", "Query template not found."),
    (TemplateConflictError, 409, "template_conflict", "查询模板冲突。", "Query template conflict."),
    (TemplateSqlError, 422, "template_sql_rejected", "查询语句未通过安全检查。", "The query text failed the safety check."),
    (ParameterError, 422, "invalid_parameter", "查询参数无效。", "A query parameter is invalid."),
    (QueryLimitError, 422, "limit_exceeded", "查询超出允许的范围。", "The query exceeds an allowed limit."),
    (BusyError, 429, "source_busy", "数据源繁忙，请稍后重试。", "The data source is busy. Try again shortly."),
    (LayoutError, 500, "layout_mismatch", "数据源表结构与配置不一致。", "The data source schema does not match its configuration."),
    (AdapterError, 400, "datasource_error", "数据源请求无法完成。", "The data source request could not be completed."),
]  # fmt: skip


def _body(code: str, zh: str, en: str, detail: str | None = None) -> dict:
    return ApiError(
        code=code, message=LocalizedText(zh=zh, en=en), detail={"reason": detail} if detail else None
    ).model_dump()


def install(app: FastAPI) -> None:
    for exc_type, status_code, code, zh, en in ERRORS:

        def handler(_req: Request, exc: Exception, s=status_code, c=code, z=zh, e=en) -> JSONResponse:
            return JSONResponse(_body(c, z, e, str(exc) or None), status_code=s)

        app.add_exception_handler(exc_type, handler)

    def db_error(_req: Request, exc: Exception) -> JSONResponse:
        text = str(getattr(exc, "orig", exc)).lower()
        log.warning("database error: %s", type(exc).__name__)
        if "statement timeout" in text or "canceling statement" in text:
            return JSONResponse(_body("query_timeout", "查询超时。", "The query timed out."), status_code=504)
        return JSONResponse(
            _body("database_error", "数据库请求失败。", "The database request failed."), status_code=502
        )

    app.add_exception_handler(SQLAlchemyError, db_error)
