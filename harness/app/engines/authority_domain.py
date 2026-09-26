from __future__ import annotations

"""First-class Runtime Authority domain model.

These structures implement Slice A of FS-RAI-R2-AUTHORITY-RESOLUTION-
ARCHITECTURE.  They model authority facts; they do not themselves establish
that supplied facts are authoritative or that an operation is admissible.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class AuthorityUsageMode(str, Enum):
    SINGLE = "single"
    BOUNDED = "bounded"
    AGGREGATE = "aggregate"
    RENEWABLE = "renewable"
    WINDOWED = "windowed"
    OTHER = "other"


class AuthorityUsageState(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    CONSUMED = "consumed"
    RELEASED = "released"
    QUARANTINED = "quarantined"


@dataclass(frozen=True)
class AuthoritySemanticsSet:
    semantics_set_id: str
    version: str
    authoritative_source_id: str
    source_competence_id: str
    protected_operation_class: str
    required_proposition_schema_id: str
    derivation_rule_set_id: str
    delegation_semantics_id: str
    approval_semantics_id: str
    parameterisation_semantics_id: str
    usage_semantics_id: str
    topology_semantics_id: str
    revalidation_semantics_id: str
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    supersession_marker: str | None = None


@dataclass(frozen=True)
class AuthorityPropositionEvidence:
    evidence_id: str
    proposition_id: str
    semantic_definition_id: str
    subject_binding: str
    purpose_context_binding: str
    observed_value: Any
    authoritative_source_id: str
    source_competence_id: str
    source_version: str
    observed_at: datetime
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    supersession_marker: str | None = None
    finality_state: str | None = None
    provenance_identity: str | None = None


@dataclass(frozen=True)
class AuthorityDerivationEdge:
    parent_node_id: str
    child_node_id: str
    derivation_rule_id: str


@dataclass(frozen=True)
class AuthorityDerivationGraph:
    graph_id: str
    root_node_ids: tuple[str, ...]
    node_ids: tuple[str, ...]
    edges: tuple[AuthorityDerivationEdge, ...]
    dependency_closure_id: str


@dataclass(frozen=True)
class EffectiveAuthorityScope:
    scope_id: str
    authority_subject_id: str
    principal_id: str
    action: str
    target: str
    mandate_id: str
    max_amount: Decimal | None
    currency: str | None
    source_accounts: tuple[str, ...]
    beneficiary_scope_id: str | None
    purpose_scope_id: str | None
    derivation_graph_id: str


@dataclass(frozen=True)
class AuthorityResolutionContext:
    context_id: str
    semantics_set_id: str
    authority_subject_id: str
    protected_operation_class: str
    authority_epoch_id: str
    authority_scope_owner_id: str
    authority_scope_ownership_epoch: str
    source_topology_generation: str
    evidence_member_ids: tuple[str, ...]
    derivation_graph_id: str
    source_version_vector_id: str
    authority_cut_id: str
    compatibility_rule_id: str
    resolved_at: datetime
    valid_until: datetime | None = None
    watermark_id: str | None = None
    fence_id: str | None = None


@dataclass(frozen=True)
class AuthorityUsagePolicy:
    usage_policy_id: str
    authority_scope_id: str
    mode: AuthorityUsageMode
    scope_key: str
    capacity: Decimal | int | None
    window_id: str | None
    disposition_rule_id: str


@dataclass(frozen=True)
class AuthorityUsageReservation:
    reservation_id: str
    usage_policy_id: str
    authority_exercise_id: str
    execution_attempt_id: str
    reserved_amount_or_units: Decimal | int | None
    state: AuthorityUsageState


@dataclass(frozen=True)
class AuthorityUsageDisposition:
    disposition_id: str
    reservation_id: str
    from_state: AuthorityUsageState
    to_state: AuthorityUsageState
    disposition_rule_id: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class ProtectedOperation:
    operation_id: str
    institutional_operation_id: str
    operation_class: str
    principal_id: str
    actor_id: str
    action: str
    target: str
    source_account: str | None
    beneficiary_id: str | None
    beneficiary_account: str | None
    amount: Decimal | None
    currency: str | None
    purpose: str | None
    mandate_id: str | None
    route_id: str | None
    executor_id: str | None
    parameter_envelope_id: str | None
    materialization_id: str


@dataclass(frozen=True)
class AuthorityOperationBinding:
    binding_id: str
    effective_authority_scope_id: str
    protected_operation_id: str
    parameter_binding_id: str | None
    approval_binding_id: str | None
    route_binding_id: str | None


@dataclass(frozen=True)
class AuthorisedExecutionConstraint:
    constraint_id: str
    authority_operation_binding_id: str
    resolution_context_id: str
    authority_exercise_id: str
    execution_attempt_id: str
    valid_until: datetime | None
    integrity_material_id: str
