from __future__ import annotations

"""Authority Resolution Engine — R2 Slice C.

Builds one coherent AuthorityResolutionContext from applicable semantics,
authoritative proposition evidence and a bounded derivation graph.

This reference implementation is intentionally fail-closed.  It does not
promote request-presented values into authority facts.
"""

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal

from app.engines.authority_domain import (
    AuthorityDerivationEdge,
    AuthorityDerivationGraph,
    AuthorityPropositionEvidence,
    AuthorityResolutionContext,
    AuthoritySemanticsSet,
    EffectiveAuthorityScope,
)
from app.engines.authority_evidence_adapters import (
    get_actor_authority_evidence,
    get_operational_authority_evidence,
)
from app.engines.institutional_authority import get_authority_snapshot, get_authority_compatibility_cut
from app.engines.approval_authority import resolve_approval


_REQUIRED_PROPOSITIONS = (
    "actor.authenticated",
    "actor.kya_status",
    "actor.role",
    "mandate.active",
    "mandate.action",
    "mandate.targets",
    "mandate.beneficiaries",
    "mandate.max_amount",
    "mandate.currency",
    "mandate.source_accounts",
    "counterparty.status",
    "account.status",
    "risk.state",
    "beneficiary.account_references",
)


class AuthorityResolutionError(RuntimeError):
    pass


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _stable_id(prefix: str, payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return f"{prefix}-{hashlib.sha256(raw).hexdigest()}"


def _mandate_evidence(snapshot, *, observed_at: datetime
                      ) -> tuple[AuthorityPropositionEvidence, ...]:
    mandate = snapshot.mandate
    source = snapshot.authoritative_source_id
    competence = snapshot.source_competence_root_id
    version = f"{snapshot.authority_epoch_id}:{snapshot.authority_fence}"
    purpose = "treasury.payment"

    values = (
        ("mandate.active", mandate.status == "ACTIVE"),
        ("mandate.action", mandate.action),
        ("mandate.targets", tuple(mandate.targets)),
        ("mandate.beneficiaries", tuple(mandate.beneficiaries)),
        ("mandate.max_amount", mandate.max_amount),
        ("mandate.currency", mandate.currency),
        ("mandate.source_accounts", tuple(mandate.source_accounts)),
    )
    result = []
    for proposition_id, value in values:
        payload = {
            "snapshot_id": snapshot.snapshot_id,
            "proposition_id": proposition_id,
            "subject": mandate.mandate_id,
            "value": str(value),
            "source_version": version,
        }
        result.append(
            AuthorityPropositionEvidence(
                evidence_id=_stable_id("EVID", payload),
                proposition_id=proposition_id,
                semantic_definition_id=f"NORM-PAY-001:{proposition_id}",
                subject_binding=mandate.mandate_id,
                purpose_context_binding=purpose,
                observed_value=value,
                authoritative_source_id=source,
                source_competence_id=competence,
                source_version=version,
                observed_at=observed_at,
                provenance_identity=snapshot.snapshot_id,
            )
        )
    return tuple(result)


def _semantics(snapshot) -> AuthoritySemanticsSet:
    return AuthoritySemanticsSet(
        semantics_set_id=snapshot.semantics.definition_id,
        version=snapshot.semantics.version,
        authoritative_source_id=snapshot.semantics.source_id,
        source_competence_id=snapshot.semantics.source_competence_root_id,
        protected_operation_class="treasury.payment",
        required_proposition_schema_id="NORM-PAY-001:required-propositions:v1",
        derivation_rule_set_id="NORM-PAY-001:derivation:v1",
        delegation_semantics_id="NORM-PAY-001:delegation:v1",
        approval_semantics_id="NORM-PAY-001:approval:v1",
        parameterisation_semantics_id="NORM-PAY-001:parameterisation:v1",
        usage_semantics_id="NORM-PAY-001:usage:v1",
        topology_semantics_id="NORM-PAY-001:topology:v1",
        revalidation_semantics_id="NORM-PAY-001:revalidation:v1",
    )


def _evidence_index(evidence: tuple[AuthorityPropositionEvidence, ...]
                    ) -> dict[str, AuthorityPropositionEvidence]:
    index: dict[str, AuthorityPropositionEvidence] = {}
    for item in evidence:
        if item.proposition_id in index:
            raise AuthorityResolutionError(
                f"conflicting/duplicate proposition evidence: {item.proposition_id}"
            )
        index[item.proposition_id] = item
    return index


def resolve_payment_authority(req, *, resolved_at: datetime
                              ) -> tuple[
                                  AuthoritySemanticsSet,
                                  tuple[AuthorityPropositionEvidence, ...],
                                  AuthorityDerivationGraph,
                                  EffectiveAuthorityScope,
                                  AuthorityResolutionContext,
                              ]:
    """Resolve the bounded reference payment authority context.

    Raises AuthorityResolutionError where required authoritative state is absent,
    incomplete, incompatible or does not support the proposed operation.
    """
    at = _aware(resolved_at)
    snapshot = get_authority_snapshot(req.mandate_id)
    if snapshot is None:
        raise AuthorityResolutionError("authoritative mandate not found")

    if snapshot.mandate.principal_id != req.principal_id:
        raise AuthorityResolutionError("mandate principal mismatch")

    evidence = (
        get_actor_authority_evidence(req.actor_id, req.principal_id, observed_at=at)
        + _mandate_evidence(snapshot, observed_at=at)
        + get_operational_authority_evidence(req.beneficiary, observed_at=at)
    )
    index = _evidence_index(evidence)
    missing = tuple(p for p in _REQUIRED_PROPOSITIONS if p not in index)
    if missing:
        raise AuthorityResolutionError(
            "required authoritative propositions unresolved: " + ", ".join(missing)
        )

    # Completeness must be established before cross-source compatibility is
    # evaluated. Missing authority evidence is an unresolved proposition, not
    # an internal lookup failure.
    #
    # A version vector records which source generations were observed; it does
    # not establish that independently versioned sources form one compatible
    # authority cut. Require an explicit reference compatibility assertion.
    actor_source_version = index["actor.authenticated"].source_version
    operational_source_version = index["counterparty.status"].source_version
    compatibility_cut = get_authority_compatibility_cut(
        req.mandate_id,
        actor_source_version=actor_source_version,
        operational_source_version=operational_source_version,
    )
    if compatibility_cut is None:
        raise AuthorityResolutionError("compatible multi-source authority cut not established")

    required_values = {
        "actor.authenticated": True,
        "actor.kya_status": "VERIFIED",
        "mandate.active": True,
        "mandate.action": req.action,
        "mandate.currency": req.currency,
        "counterparty.status": "APPROVED",
        "account.status": "ACTIVE",
        "risk.state": "NORMAL",
    }
    for proposition_id, expected in required_values.items():
        if index[proposition_id].observed_value != expected:
            raise AuthorityResolutionError(
                f"authoritative proposition does not support operation: {proposition_id}"
            )

    if req.target not in index["mandate.targets"].observed_value:
        raise AuthorityResolutionError("target outside authoritative mandate scope")
    if req.beneficiary not in index["mandate.beneficiaries"].observed_value:
        raise AuthorityResolutionError("beneficiary outside authoritative mandate scope")
    if req.beneficiary_account_reference not in index["beneficiary.account_references"].observed_value:
        raise AuthorityResolutionError("beneficiary account does not correspond to authorised beneficiary")
    if req.source_account not in index["mandate.source_accounts"].observed_value:
        raise AuthorityResolutionError("source account outside effective mandate")
    if req.amount > index["mandate.max_amount"].observed_value:
        raise AuthorityResolutionError("amount outside effective mandate")

    semantics = _semantics(snapshot)
    try:
        approval = resolve_approval(req, operation_class="treasury.payment", resolved_at=at)
    except ValueError as exc:
        raise AuthorityResolutionError(str(exc)) from exc
    root_id = f"ROOT:{req.principal_id}:{req.mandate_id}"
    subject_id = f"SUBJECT:{req.actor_id}"
    scope_payload = {
        "root": root_id,
        "subject": subject_id,
        "action": req.action,
        "target": req.target,
        "mandate": req.mandate_id,
        "snapshot": snapshot.snapshot_id,
        "approval_binding_id": approval.approval_binding_id,
        "approval_rule_id": approval.approval_rule_id,
    }
    scope_id = _stable_id("SCOPE", scope_payload)
    graph = AuthorityDerivationGraph(
        graph_id=_stable_id("GRAPH", scope_payload),
        root_node_ids=(root_id,),
        node_ids=(root_id, subject_id, scope_id),
        edges=(
            AuthorityDerivationEdge(root_id, subject_id, "NORM-PAY-001:delegation:v1"),
            AuthorityDerivationEdge(subject_id, scope_id, "NORM-PAY-001:scope:v1"),
            AuthorityDerivationEdge(root_id, scope_id, approval.approval_rule_id),
        ),
        dependency_closure_id=_stable_id(
            "DEPS", {"evidence": sorted(item.evidence_id for item in evidence)}
        ),
    )
    scope = EffectiveAuthorityScope(
        scope_id=scope_id,
        authority_subject_id=req.actor_id,
        principal_id=req.principal_id,
        action=snapshot.mandate.action,
        target=req.target,
        mandate_id=req.mandate_id,
        max_amount=snapshot.mandate.max_amount,
        currency=snapshot.mandate.currency,
        source_accounts=tuple(snapshot.mandate.source_accounts),
        beneficiary_scope_id=req.beneficiary,
        purpose_scope_id=req.purpose,
        derivation_graph_id=graph.graph_id,
    )

    context_payload = {
        "semantics": semantics.semantics_set_id,
        "subject": req.actor_id,
        "snapshot": snapshot.snapshot_id,
        "evidence": sorted(item.evidence_id for item in evidence),
        "graph": graph.graph_id,
        "epoch": snapshot.authority_epoch_id,
        "fence": snapshot.authority_fence,
        "approval_binding_id": approval.approval_binding_id,
        "approval_rule_id": approval.approval_rule_id,
        "compatibility_cut_id": compatibility_cut.compatibility_cut_id,
    }
    context = AuthorityResolutionContext(
        context_id=_stable_id("CTX", context_payload),
        semantics_set_id=semantics.semantics_set_id,
        authority_subject_id=req.actor_id,
        protected_operation_class="treasury.payment",
        authority_epoch_id=snapshot.authority_epoch_id,
        authority_scope_owner_id=snapshot.authoritative_source_id,
        authority_scope_ownership_epoch=snapshot.authority_epoch_id,
        source_topology_generation=snapshot.authority_epoch_id,
        evidence_member_ids=tuple(sorted(item.evidence_id for item in evidence)),
        derivation_graph_id=graph.graph_id,
        source_version_vector_id=_stable_id(
            "VV",
            {item.evidence_id: item.source_version for item in evidence},
        ),
        authority_cut_id=snapshot.snapshot_id,
        compatibility_rule_id="NORM-PAY-001:compatibility:v1",
        resolved_at=at,
        watermark_id=f"FENCE:{snapshot.authority_fence}",
        fence_id=f"{snapshot.authority_fence_scope_key}:{snapshot.authority_fence}",
    )
    return semantics, evidence, graph, scope, context
