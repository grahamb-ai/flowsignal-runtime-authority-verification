from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

@dataclass
class FinancialAuthorityRequest:
    scenario_id: str
    action: str
    target: str
    actor_id: str
    actor_type: str
    actor_role: str
    actor_authenticated: bool
    kya_status: str
    principal_id: str
    principal_name: str
    mandate_id: str
    mandate_status: str
    mandate_max_amount: Decimal
    mandate_currency: str
    permitted_source_accounts: list[str]
    permitted_counterparty_class: str
    mandate_valid_until: datetime
    amount: Decimal
    currency: str
    source_account: str
    beneficiary: str
    beneficiary_account_reference: str
    purpose: str
    counterparty_status: str
    account_status: str
    risk_state: str
    approval_required: bool
    screening_status: str
    screening_captured_at: datetime
    screening_max_age_seconds: int
    screening_source: str
    requested_execution_time: datetime
    institutional_operation_id: str | None = None

@dataclass
class FinancialCheck:
    name: str
    passed: bool
    outcome_on_failure: str
    reason: str | None = None
    evidence_ref: str | None = None

@dataclass
class ExecutionResponse:
    decision: str
    reason_code: str
    authority_receipt_id: str
    valid_until: datetime | None
    required_action: str | None = None

@dataclass
class AuthorityReceipt:
    id: str
    scenario_id: str
    decision: str
    reason_code: str
    sealed_at: datetime
    valid_until: datetime | None
    action_binding_hash: str
    authority_state_version: int
    authority_snapshot_id: str
    authority_subject_principal_id: str
    authority_subject_mandate_id: str
    authority_epoch_id: str
    authority_fence_scope_key: str
    authority_fence: int
    authoritative_source_id: str
    source_competence_root_id: str
    authority_semantics_version: str
    authority_semantics_definition_id: str
    authority_semantics_source_id: str
    receipt_hmac: str
    request_snapshot: dict[str, Any]
    checks: list[FinancialCheck] = field(default_factory=list)
    evidence_references: list[dict[str, Any]] = field(default_factory=list)
