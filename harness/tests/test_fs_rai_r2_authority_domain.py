from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.engines.authority_domain import (
    AuthorityDerivationEdge,
    AuthorityDerivationGraph,
    AuthorityOperationBinding,
    AuthorityPropositionEvidence,
    AuthorityResolutionContext,
    AuthoritySemanticsSet,
    AuthorityUsageMode,
    AuthorityUsagePolicy,
    AuthorityUsageReservation,
    AuthorityUsageState,
    AuthorisedExecutionConstraint,
    EffectiveAuthorityScope,
    ProtectedOperation,
)


NOW = datetime(2026, 9, 24, tzinfo=timezone.utc)


def test_slice_a_models_are_immutable_and_identity_bearing():
    semantics = AuthoritySemanticsSet(
        semantics_set_id="SEM-1",
        version="1",
        authoritative_source_id="SRC-POLICY",
        source_competence_id="COMP-POLICY",
        protected_operation_class="treasury.payment",
        required_proposition_schema_id="PROPSET-1",
        derivation_rule_set_id="RULESET-1",
        delegation_semantics_id="DEL-1",
        approval_semantics_id="APP-1",
        parameterisation_semantics_id="PARAM-1",
        usage_semantics_id="USE-1",
        topology_semantics_id="TOPO-1",
        revalidation_semantics_id="REVAL-1",
    )
    evidence = AuthorityPropositionEvidence(
        evidence_id="E-1",
        proposition_id="mandate.active",
        semantic_definition_id="DEF-1",
        subject_binding="MANDATE-1",
        purpose_context_binding="treasury.payment",
        observed_value=True,
        authoritative_source_id="SRC-MANDATE",
        source_competence_id="COMP-MANDATE",
        source_version="17",
        observed_at=NOW,
    )
    graph = AuthorityDerivationGraph(
        graph_id="G-1",
        root_node_ids=("ROOT-1",),
        node_ids=("ROOT-1", "SCOPE-1"),
        edges=(AuthorityDerivationEdge("ROOT-1", "SCOPE-1", "RULE-1"),),
        dependency_closure_id="DEP-1",
    )
    scope = EffectiveAuthorityScope(
        scope_id="SCOPE-1",
        authority_subject_id="ACTOR-1",
        principal_id="P-1",
        action="payment.release",
        target="GATEWAY",
        mandate_id="MANDATE-1",
        max_amount=Decimal("1000.00"),
        currency="GBP",
        source_accounts=("TREASURY-1",),
        beneficiary_scope_id=None,
        purpose_scope_id=None,
        derivation_graph_id=graph.graph_id,
    )
    context = AuthorityResolutionContext(
        context_id="CTX-1",
        semantics_set_id=semantics.semantics_set_id,
        authority_subject_id=scope.authority_subject_id,
        protected_operation_class="treasury.payment",
        authority_epoch_id="EPOCH-1",
        authority_scope_owner_id="OWNER-1",
        authority_scope_ownership_epoch="OWN-EPOCH-1",
        source_topology_generation="GEN-1",
        evidence_member_ids=(evidence.evidence_id,),
        derivation_graph_id=graph.graph_id,
        source_version_vector_id="VV-1",
        authority_cut_id="CUT-1",
        compatibility_rule_id="COMPAT-1",
        resolved_at=NOW,
    )
    policy = AuthorityUsagePolicy(
        usage_policy_id="UP-1",
        authority_scope_id=scope.scope_id,
        mode=AuthorityUsageMode.SINGLE,
        scope_key="MANDATE-1",
        capacity=1,
        window_id=None,
        disposition_rule_id="DISP-1",
    )
    reservation = AuthorityUsageReservation(
        reservation_id="RES-1",
        usage_policy_id=policy.usage_policy_id,
        authority_exercise_id="EX-1",
        execution_attempt_id="ATT-1",
        reserved_amount_or_units=1,
        state=AuthorityUsageState.RESERVED,
    )
    operation = ProtectedOperation(
        operation_id="OP-1",
        institutional_operation_id="INST-OP-1",
        operation_class="treasury.payment",
        principal_id="P-1",
        actor_id="ACTOR-1",
        action="payment.release",
        target="GATEWAY",
        source_account="TREASURY-1",
        beneficiary_id="SUPPLIER-X",
        beneficiary_account="ACC-X",
        amount=Decimal("900.00"),
        currency="GBP",
        purpose="invoice",
        mandate_id="MANDATE-1",
        route_id="R1",
        executor_id="EXEC-1",
        parameter_envelope_id=None,
        materialization_id="MAT-1",
    )
    binding = AuthorityOperationBinding(
        binding_id="BIND-1",
        effective_authority_scope_id=scope.scope_id,
        protected_operation_id=operation.operation_id,
        parameter_binding_id=None,
        approval_binding_id=None,
        route_binding_id="RB-1",
    )
    constraint = AuthorisedExecutionConstraint(
        constraint_id="C-1",
        authority_operation_binding_id=binding.binding_id,
        resolution_context_id=context.context_id,
        authority_exercise_id=reservation.authority_exercise_id,
        execution_attempt_id=reservation.execution_attempt_id,
        valid_until=None,
        integrity_material_id="INT-1",
    )

    assert constraint.resolution_context_id == "CTX-1"
    assert operation.amount == Decimal("900.00")
    with pytest.raises(FrozenInstanceError):
        operation.amount = Decimal("901.00")


def test_usage_mode_and_state_are_not_free_form_strings():
    assert AuthorityUsageMode.AGGREGATE.value == "aggregate"
    assert AuthorityUsageState.QUARANTINED.value == "quarantined"
