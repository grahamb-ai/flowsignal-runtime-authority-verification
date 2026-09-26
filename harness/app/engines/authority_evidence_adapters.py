from __future__ import annotations

"""Bounded authoritative evidence adapters for the reference payment model.

The request is a proposal, not an authority database.  These adapters turn
reference institutional state into AuthorityPropositionEvidence.  Unknown
subjects/propositions return no evidence and therefore cannot be promoted from
request-presented values.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal
from threading import RLock

from app.engines.authority_domain import AuthorityPropositionEvidence


@dataclass(frozen=True)
class AuthoritativeActorStanding:
    actor_id: str
    principal_id: str
    authenticated: bool
    kya_status: str
    role: str
    source_version: str


@dataclass(frozen=True)
class AuthoritativeOperationalStanding:
    beneficiary_id: str
    counterparty_status: str
    account_status: str
    risk_state: str
    authorised_account_references: tuple[str, ...]
    source_version: str


_LOCK = RLock()
_ACTOR_SOURCE = "INSTITUTIONAL-IDENTITY-STANDING-001"
_ACTOR_COMPETENCE = "COMPETENCE:IDENTITY-STANDING"
_OPERATION_SOURCE = "INSTITUTIONAL-OPERATIONAL-STANDING-001"
_OPERATION_COMPETENCE = "COMPETENCE:OPERATIONAL-STANDING"

_ACTORS = {
    "agent-treasury-01": AuthoritativeActorStanding(
        actor_id="agent-treasury-01",
        principal_id="institution-001",
        authenticated=True,
        kya_status="VERIFIED",
        role="treasury-agent",
        source_version="1",
    )
}

_OPERATIONAL = {
    "SUPPLIER-X": AuthoritativeOperationalStanding(
        beneficiary_id="SUPPLIER-X",
        counterparty_status="APPROVED",
        account_status="ACTIVE",
        risk_state="NORMAL",
        authorised_account_references=("ACCT-SUPPLIER-X-001",),
        source_version="1",
    )
}


def _now(observed_at: datetime | None) -> datetime:
    value = observed_at or datetime.now(timezone.utc)
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _evidence_id(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _evidence(*, proposition_id: str, semantic_definition_id: str,
              subject_binding: str, purpose_context_binding: str,
              observed_value, source_id: str, competence_id: str,
              source_version: str, observed_at: datetime) -> AuthorityPropositionEvidence:
    payload = {
        "proposition_id": proposition_id,
        "semantic_definition_id": semantic_definition_id,
        "subject_binding": subject_binding,
        "purpose_context_binding": purpose_context_binding,
        "observed_value": observed_value,
        "source_id": source_id,
        "competence_id": competence_id,
        "source_version": source_version,
        "observed_at": observed_at.isoformat(),
    }
    return AuthorityPropositionEvidence(
        evidence_id=_evidence_id(payload),
        proposition_id=proposition_id,
        semantic_definition_id=semantic_definition_id,
        subject_binding=subject_binding,
        purpose_context_binding=purpose_context_binding,
        observed_value=observed_value,
        authoritative_source_id=source_id,
        source_competence_id=competence_id,
        source_version=source_version,
        observed_at=observed_at,
        provenance_identity=f"{source_id}:{source_version}",
    )


def get_actor_authority_evidence(actor_id: str, principal_id: str, *,
                                 observed_at: datetime | None = None
                                 ) -> tuple[AuthorityPropositionEvidence, ...]:
    at = _now(observed_at)
    with _LOCK:
        standing = _ACTORS.get(actor_id)
        if standing is None or standing.principal_id != principal_id:
            return ()
        return (
            _evidence(
                proposition_id="actor.authenticated",
                semantic_definition_id="NORM-PAY-001:actor.authenticated",
                subject_binding=actor_id,
                purpose_context_binding=principal_id,
                observed_value=standing.authenticated,
                source_id=_ACTOR_SOURCE,
                competence_id=_ACTOR_COMPETENCE,
                source_version=standing.source_version,
                observed_at=at,
            ),
            _evidence(
                proposition_id="actor.kya_status",
                semantic_definition_id="NORM-PAY-001:actor.kya_status",
                subject_binding=actor_id,
                purpose_context_binding=principal_id,
                observed_value=standing.kya_status,
                source_id=_ACTOR_SOURCE,
                competence_id=_ACTOR_COMPETENCE,
                source_version=standing.source_version,
                observed_at=at,
            ),
            _evidence(
                proposition_id="actor.role",
                semantic_definition_id="NORM-PAY-001:actor.role",
                subject_binding=actor_id,
                purpose_context_binding=principal_id,
                observed_value=standing.role,
                source_id=_ACTOR_SOURCE,
                competence_id=_ACTOR_COMPETENCE,
                source_version=standing.source_version,
                observed_at=at,
            ),
        )


def get_operational_authority_evidence(beneficiary_id: str, *,
                                       observed_at: datetime | None = None
                                       ) -> tuple[AuthorityPropositionEvidence, ...]:
    at = _now(observed_at)
    with _LOCK:
        standing = _OPERATIONAL.get(beneficiary_id)
        if standing is None:
            return ()
        values = (
            ("counterparty.status", standing.counterparty_status),
            ("account.status", standing.account_status),
            ("risk.state", standing.risk_state),
            ("beneficiary.account_references", standing.authorised_account_references),
        )
        return tuple(
            _evidence(
                proposition_id=prop,
                semantic_definition_id=f"NORM-PAY-001:{prop}",
                subject_binding=beneficiary_id,
                purpose_context_binding="treasury.payment",
                observed_value=value,
                source_id=_OPERATION_SOURCE,
                competence_id=_OPERATION_COMPETENCE,
                source_version=standing.source_version,
                observed_at=at,
            )
            for prop, value in values
        )


def set_actor_source_version_for_test(actor_id: str, source_version: str) -> None:
    """Test/reference-harness support: advance one authoritative source independently."""
    global _ACTORS
    with _LOCK:
        standing = _ACTORS.get(actor_id)
        if standing is None:
            raise ValueError("unknown actor")
        _ACTORS[actor_id] = AuthoritativeActorStanding(
            actor_id=standing.actor_id,
            principal_id=standing.principal_id,
            authenticated=standing.authenticated,
            kya_status=standing.kya_status,
            role=standing.role,
            source_version=source_version,
        )


def set_operational_source_version_for_test(beneficiary_id: str, source_version: str) -> None:
    """Test/reference-harness support: advance operational standing independently."""
    global _OPERATIONAL
    with _LOCK:
        standing = _OPERATIONAL.get(beneficiary_id)
        if standing is None:
            raise ValueError("unknown beneficiary")
        _OPERATIONAL[beneficiary_id] = AuthoritativeOperationalStanding(
            beneficiary_id=standing.beneficiary_id,
            counterparty_status=standing.counterparty_status,
            account_status=standing.account_status,
            risk_state=standing.risk_state,
            authorised_account_references=standing.authorised_account_references,
            source_version=source_version,
        )


def register_operational_standing_for_test(
    beneficiary_id: str,
    *,
    counterparty_status: str = "APPROVED",
    account_status: str = "ACTIVE",
    risk_state: str = "NORMAL",
    source_version: str = "1",
    authorised_account_references: tuple[str, ...] = (),
) -> None:
    """Test/reference-harness support for an independently known beneficiary."""
    with _LOCK:
        _OPERATIONAL[beneficiary_id] = AuthoritativeOperationalStanding(
            beneficiary_id=beneficiary_id,
            counterparty_status=counterparty_status,
            account_status=account_status,
            risk_state=risk_state,
            authorised_account_references=authorised_account_references,
            source_version=source_version,
        )
