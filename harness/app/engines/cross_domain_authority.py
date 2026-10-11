from __future__ import annotations

"""Bounded reference adapter for cross-domain authority-state observations.

This module models Domain D independently authenticating and freshness-checking
an authority-state assertion made by Domain A.  It is a reference harness seam,
not a production PKI, federation, transparency-log or consensus mechanism.
"""

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import hmac
import json
from threading import RLock


@dataclass(frozen=True)
class CrossDomainAuthorityObservation:
    issuer_domain: str
    authority_id: str
    authority_subject: str
    status: str
    authority_epoch: int
    effective_at: str
    observed_at: str
    valid_until: str
    permitted_actions: tuple[str, ...]
    permitted_resources: tuple[str, ...]
    parent_permitted_actions: tuple[str, ...]
    parent_permitted_resources: tuple[str, ...]
    root_authority_id: str
    parent_authority_id: str
    policy_id: str
    evidence_digest: str
    signature: str = ""


@dataclass(frozen=True)
class CrossDomainAuthorityBinding:
    issuer_domain: str
    authority_id: str
    authority_subject: str
    authority_epoch: int
    observation_digest: str
    policy_id: str
    evidence_digest: str
    root_authority_id: str
    parent_authority_id: str


_LOCK = RLock()
_TRUST_ANCHORS: dict[str, bytes] = {}
_EXPECTED_ISSUERS: dict[tuple[str, str], str] = {}
_OBSERVATIONS: dict[tuple[str, str], CrossDomainAuthorityObservation] = {}
_TRUST_ADMIN_CAPABILITY = object()


def _aware(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _unsigned_payload(observation: CrossDomainAuthorityObservation) -> bytes:
    payload = asdict(observation)
    payload.pop("signature")
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()


def observation_digest(observation: CrossDomainAuthorityObservation) -> str:
    return hashlib.sha256(_unsigned_payload(observation)).hexdigest()


def sign_observation_for_test(
    observation: CrossDomainAuthorityObservation, *, reference_key: bytes
) -> CrossDomainAuthorityObservation:
    """Reference-fixture signer; not a production signing facility."""
    signature = hmac.new(reference_key, _unsigned_payload(observation), hashlib.sha256).hexdigest()
    return replace(observation, signature=signature)


def register_trust_anchor_for_test(
    *, issuer_domain: str, reference_key: bytes, capability: object | None = None
) -> None:
    if capability is not _TRUST_ADMIN_CAPABILITY:
        raise PermissionError("cross-domain trust-anchor administration required")
    if not issuer_domain or not reference_key:
        raise ValueError("issuer domain and trust anchor required")
    with _LOCK:
        _TRUST_ANCHORS[issuer_domain] = bytes(reference_key)


def enroll_external_authority_for_test(
    *,
    authority_id: str,
    authority_subject: str,
    issuer_domain: str,
    capability: object | None = None,
) -> None:
    if capability is not _TRUST_ADMIN_CAPABILITY:
        raise PermissionError("cross-domain authority enrollment required")
    with _LOCK:
        if issuer_domain not in _TRUST_ANCHORS:
            raise ValueError("issuer trust anchor not established")
        _EXPECTED_ISSUERS[(authority_id, authority_subject)] = issuer_domain


def ingest_authority_observation(
    observation: CrossDomainAuthorityObservation, *, verified_at: datetime
) -> CrossDomainAuthorityObservation:
    """Authenticate, freshness-check and monotonically accept Domain A state."""
    now = _aware(verified_at)
    with _LOCK:
        expected_issuer = _EXPECTED_ISSUERS.get(
            (observation.authority_id, observation.authority_subject)
        )
        key = _TRUST_ANCHORS.get(observation.issuer_domain)
        if expected_issuer != observation.issuer_domain or key is None:
            raise ValueError("implicit cross-domain authority transfer rejected")

        expected_signature = hmac.new(
            key, _unsigned_payload(observation), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(expected_signature, observation.signature):
            raise ValueError("cross-domain authority observation authenticity invalid")

        if observation.status not in {"ACTIVE", "REVOKED"}:
            raise ValueError("cross-domain authority state unresolved")
        if observation.authority_epoch < 1:
            raise ValueError("cross-domain authority epoch invalid")
        if not observation.policy_id or not observation.evidence_digest:
            raise ValueError("cross-domain policy/evidence binding required")
        if not observation.root_authority_id or not observation.parent_authority_id:
            raise ValueError("complete delegation lineage required")
        if not set(observation.permitted_actions).issubset(
            observation.parent_permitted_actions
        ):
            raise ValueError("downstream delegation expands parent action authority")
        if not set(observation.permitted_resources).issubset(
            observation.parent_permitted_resources
        ):
            raise ValueError("downstream delegation expands parent resource authority")

        effective_at = _aware(observation.effective_at)
        observed_at = _aware(observation.observed_at)
        valid_until = _aware(observation.valid_until)
        if effective_at > now or observed_at > now or now > valid_until:
            raise ValueError("cross-domain authority observation not current")

        identity = (observation.authority_id, observation.authority_subject)
        current = _OBSERVATIONS.get(identity)
        if current is not None and observation.authority_epoch <= current.authority_epoch:
            raise ValueError("cross-domain authority state rollback or replay rejected")
        _OBSERVATIONS[identity] = observation
        return observation


def current_authority_binding(
    *,
    authority_id: str,
    authority_subject: str,
    action: str,
    resource: str,
    at: datetime,
) -> tuple[str, CrossDomainAuthorityBinding | None]:
    """Return ACTIVE, REVOKED, UNRESOLVED, or NOT_ENROLLED for Domain D."""
    now = _aware(at)
    identity = (authority_id, authority_subject)
    with _LOCK:
        issuer = _EXPECTED_ISSUERS.get(identity)
        if issuer is None:
            return "NOT_ENROLLED", None
        observation = _OBSERVATIONS.get(identity)
        if observation is None:
            return "UNRESOLVED", None
        if observation.issuer_domain != issuer:
            return "UNRESOLVED", None
        if now > _aware(observation.valid_until) or now < _aware(observation.effective_at):
            return "UNRESOLVED", None
        if observation.status == "REVOKED":
            return "REVOKED", None
        if observation.status != "ACTIVE":
            return "UNRESOLVED", None
        if action not in observation.permitted_actions or resource not in observation.permitted_resources:
            return "UNRESOLVED", None
        return "ACTIVE", CrossDomainAuthorityBinding(
            issuer_domain=observation.issuer_domain,
            authority_id=observation.authority_id,
            authority_subject=observation.authority_subject,
            authority_epoch=observation.authority_epoch,
            observation_digest=observation_digest(observation),
            policy_id=observation.policy_id,
            evidence_digest=observation.evidence_digest,
            root_authority_id=observation.root_authority_id,
            parent_authority_id=observation.parent_authority_id,
        )


def reset_cross_domain_authority_for_test() -> None:
    with _LOCK:
        _TRUST_ANCHORS.clear()
        _EXPECTED_ISSUERS.clear()
        _OBSERVATIONS.clear()

