from __future__ import annotations

"""R3 — approval as authority semantics and derivation evidence.

Approval is not a request boolean.  The governing approval rule identifies
whether approval is required, the eligible authority subjects, quorum and
composition requirements, operation scope and temporal survival rule.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock


@dataclass(frozen=True)
class ApprovalRule:
    approval_rule_id: str
    operation_class: str
    required: bool
    quorum: int
    eligible_role_ids: tuple[str, ...]
    require_distinct_authority_subjects: bool
    required_role_ids: tuple[str, ...]
    survival_rule_id: str


@dataclass(frozen=True)
class ApprovalGrant:
    approval_grant_id: str
    approval_rule_id: str
    authority_subject_id: str
    role_id: str
    principal_id: str
    mandate_id: str
    action: str
    target: str
    source_account: str
    beneficiary_id: str
    currency: str
    max_amount_text: str
    purpose: str
    approved_at: datetime
    valid_until: datetime
    standing_version: str


@dataclass(frozen=True)
class ApprovalResolution:
    approval_binding_id: str
    approval_rule_id: str
    grant_ids: tuple[str, ...]
    authority_subject_ids: tuple[str, ...]
    resolved_at: datetime


_LOCK = RLock()
_RULES = {
    "treasury.payment": ApprovalRule(
        approval_rule_id="NORM-PAY-001:approval:v1",
        operation_class="treasury.payment",
        required=False,
        quorum=0,
        eligible_role_ids=(),
        require_distinct_authority_subjects=True,
        required_role_ids=(),
        survival_rule_id="NORM-PAY-001:approval-survival:v1",
    )
}
_GRANTS: dict[str, ApprovalGrant] = {}


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _stable_id(prefix: str, payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()}"


def get_approval_rule(operation_class: str) -> ApprovalRule | None:
    with _LOCK:
        return _RULES.get(operation_class)


def register_approval_rule(rule: ApprovalRule) -> None:
    with _LOCK:
        _RULES[rule.operation_class] = rule


def register_approval_grant(grant: ApprovalGrant) -> None:
    with _LOCK:
        _GRANTS[grant.approval_grant_id] = grant


def resolve_approval(req, *, operation_class: str, resolved_at: datetime) -> ApprovalResolution:
    at = _aware(resolved_at)
    with _LOCK:
        rule = _RULES.get(operation_class)
        if rule is None:
            raise ValueError("approval applicability unresolved")
        if not rule.required:
            return ApprovalResolution(
                approval_binding_id=_stable_id(
                    "APPROVAL",
                    {
                        "rule": rule.approval_rule_id,
                        "operation_class": operation_class,
                        "required": False,
                    },
                ),
                approval_rule_id=rule.approval_rule_id,
                grant_ids=(),
                authority_subject_ids=(),
                resolved_at=at,
            )

        candidates = []
        for grant in _GRANTS.values():
            if grant.approval_rule_id != rule.approval_rule_id:
                continue
            if not (_aware(grant.approved_at) <= at <= _aware(grant.valid_until)):
                continue
            if grant.role_id not in rule.eligible_role_ids:
                continue
            if grant.principal_id != req.principal_id or grant.mandate_id != req.mandate_id:
                continue
            if grant.action != req.action or grant.target != req.target:
                continue
            if grant.source_account != req.source_account:
                continue
            if grant.beneficiary_id != req.beneficiary or grant.currency != req.currency:
                continue
            if grant.purpose != req.purpose:
                continue
            if req.amount > __import__("decimal").Decimal(grant.max_amount_text):
                continue
            candidates.append(grant)

        subjects = {g.authority_subject_id for g in candidates}
        if rule.require_distinct_authority_subjects and len(subjects) < rule.quorum:
            raise ValueError("approval quorum not established by distinct authority subjects")
        if not rule.require_distinct_authority_subjects and len(candidates) < rule.quorum:
            raise ValueError("approval quorum not established")

        roles = {g.role_id for g in candidates}
        missing_roles = set(rule.required_role_ids) - roles
        if missing_roles:
            raise ValueError("approval composition requirement not established")

        # Select a quorum that satisfies composition, rather than taking the
        # lexicographically first N grants and checking composition only across
        # the larger candidate pool.
        selected = []
        used_subjects = set()
        for required_role in rule.required_role_ids:
            match = next(
                (
                    g for g in sorted(candidates, key=lambda x: x.approval_grant_id)
                    if g.role_id == required_role
                    and (not rule.require_distinct_authority_subjects or g.authority_subject_id not in used_subjects)
                ),
                None,
            )
            if match is None:
                raise ValueError("approval composition requirement not established")
            selected.append(match)
            used_subjects.add(match.authority_subject_id)
        for grant in sorted(candidates, key=lambda x: x.approval_grant_id):
            if len(selected) >= rule.quorum:
                break
            if grant in selected:
                continue
            if rule.require_distinct_authority_subjects and grant.authority_subject_id in used_subjects:
                continue
            selected.append(grant)
            used_subjects.add(grant.authority_subject_id)
        if len(selected) < rule.quorum:
            raise ValueError("approval quorum not established")
        payload = {
            "rule": rule.approval_rule_id,
            "grants": [g.approval_grant_id for g in selected],
            "subjects": [g.authority_subject_id for g in selected],
            "operation": {
                "principal": req.principal_id, "mandate": req.mandate_id,
                "action": req.action, "target": req.target,
                "source_account": req.source_account, "beneficiary": req.beneficiary,
                "amount": str(req.amount), "currency": req.currency, "purpose": req.purpose,
            },
        }
        return ApprovalResolution(
            approval_binding_id=_stable_id("APPROVAL", payload),
            approval_rule_id=rule.approval_rule_id,
            grant_ids=tuple(g.approval_grant_id for g in selected),
            authority_subject_ids=tuple(g.authority_subject_id for g in selected),
            resolved_at=at,
        )
