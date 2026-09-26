from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal
from threading import RLock


@dataclass(frozen=True)
class AuthoritativeMandate:
    mandate_id: str
    status: str
    max_amount: Decimal
    currency: str
    source_accounts: tuple[str, ...]
    principal_id: str
    action: str
    targets: tuple[str, ...]
    beneficiaries: tuple[str, ...]


@dataclass(frozen=True)
class AuthoritySemantics:
    version: str
    definition_id: str
    source_id: str
    source_competence_root_id: str


@dataclass(frozen=True)
class AuthoritySnapshot:
    snapshot_id: str
    authority_epoch_id: str
    usage_window_id: str
    authority_fence_scope_key: str
    authority_fence: int
    mandate_source_version: str
    authoritative_source_id: str
    source_competence_root_id: str
    semantics: AuthoritySemantics
    mandate: AuthoritativeMandate


_LOCK = RLock()
_EPOCH_ID = "AUTH-EPOCH-001"
_USAGE_WINDOW_ID = "DAY-001"
_SOURCE_ID = "INSTITUTIONAL-AUTHORITY-STORE-001"
_COMPETENCE_ROOT = "INSTITUTIONAL-COMPETENCE-ROOT-001"
_USAGE_WINDOW_TRANSITION_CAPABILITY = object()
@dataclass(frozen=True)
class AuthorityFenceTransitionCapability:
    authority_fence_scope_key: str
    source_fence: int


_AUTHORITY_FENCE_TRANSITION_CAPABILITY = AuthorityFenceTransitionCapability(
    authority_fence_scope_key="institution-001:MANDATE-TREASURY-001",
    source_fence=1,
)


def issue_authority_fence_transition_capability_for_test(
    authority_fence_scope_key: str,
) -> AuthorityFenceTransitionCapability:
    """Issue bounded reference transition authority for the current fence state.

    Test/reference-harness support only. This models competent establishment of
    transition authority; it is not a production credential mechanism.
    """
    with _LOCK:
        return AuthorityFenceTransitionCapability(
            authority_fence_scope_key=authority_fence_scope_key,
            source_fence=_FENCE,
        )
_COMPATIBILITY_CUT_REGISTRATION_CAPABILITY = object()
_COMPATIBLE_SOURCE_GENERATIONS: set[tuple[str, str, str]] = {("MANDATE-SOURCE-001", "1", "1")}
_SEMANTICS = AuthoritySemantics(
    version="NORM-PAY-001-v1.2",
    definition_id="FS-RAI-FX-001:NORM-PAY-001:v1.2",
    source_id="FS-RAI-FX-001-v1.0",
    source_competence_root_id=_COMPETENCE_ROOT,
)
_FENCE = 1
_MANDATE_SOURCE_VERSION = "MANDATE-SOURCE-001"
_MANDATES = {
    "MANDATE-TREASURY-001": AuthoritativeMandate(
        mandate_id="MANDATE-TREASURY-001",
        status="ACTIVE",
        max_amount=Decimal("1000000.00"),
        currency="GBP",
        source_accounts=("TREASURY-001",),
        principal_id="institution-001",
        action="payment.release",
        targets=("TREASURY_PAYMENT_GATEWAY",),
        beneficiaries=("SUPPLIER-X",),
    )
}


def _snapshot_id(mandate: AuthoritativeMandate, fence: int) -> str:
    payload = {
        "authority_epoch_id": _EPOCH_ID,
        "usage_window_id": _USAGE_WINDOW_ID,
        "authority_fence": fence,
        "mandate_source_version": _MANDATE_SOURCE_VERSION,
        "authoritative_source_id": _SOURCE_ID,
        "source_competence_root_id": _COMPETENCE_ROOT,
        "semantics": asdict(_SEMANTICS),
        "mandate": {
            **asdict(mandate),
            "max_amount": format(mandate.max_amount, ".2f"),
        },
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def get_authority_snapshot(mandate_id: str) -> AuthoritySnapshot | None:
    """Return one coherent immutable reference-state cut.

    Unknown mandates return None. Request-presented values are never promoted
    into authoritative state.
    """
    with _LOCK:
        mandate = _MANDATES.get(mandate_id)
        if mandate is None:
            return None
        fence = _FENCE
        return AuthoritySnapshot(
            snapshot_id=_snapshot_id(mandate, fence),
            authority_epoch_id=_EPOCH_ID,
            usage_window_id=_USAGE_WINDOW_ID,
            authority_fence_scope_key=f"{mandate.principal_id}:{mandate.mandate_id}",
            authority_fence=fence,
            mandate_source_version=_MANDATE_SOURCE_VERSION,
            authoritative_source_id=_SOURCE_ID,
            source_competence_root_id=_COMPETENCE_ROOT,
            semantics=_SEMANTICS,
            mandate=mandate,
        )



def advance_authority_semantics_source_for_test() -> AuthoritySemantics:
    """Replace the authoritative semantics identity while preserving proposition values.

    Test/reference-harness support only. Returns the previous semantics object
    so destructive hostile tests can restore process-global reference state.
    """
    global _SEMANTICS, _FENCE
    with _LOCK:
        previous = _SEMANTICS
        _SEMANTICS = AuthoritySemantics(
            version=previous.version,
            definition_id=f"{previous.definition_id}:NEXT",
            source_id=f"{previous.source_id}:NEXT",
            source_competence_root_id=previous.source_competence_root_id,
        )
        _FENCE += 1
        return previous


def restore_authority_semantics_for_test(previous: AuthoritySemantics) -> None:
    """Restore semantics after a destructive reference-harness hostile test."""
    global _SEMANTICS, _FENCE
    with _LOCK:
        _SEMANTICS = previous
        _FENCE += 1

def advance_authority_fence(
    *,
    transition_capability: object | None = None,
    authority_fence_scope_key: str = "institution-001:MANDATE-TREASURY-001",
) -> int:
    """Advance authority state only under scope-correspondent transition authority.

    Reference-harness mechanism only. The capability is bound to one frozen
    authority-fence scope; possession does not imply authority over another
    principal/mandate domain.
    """
    global _FENCE
    if not isinstance(transition_capability, AuthorityFenceTransitionCapability):
        raise PermissionError("authoritative fence transition required")
    if transition_capability.authority_fence_scope_key != authority_fence_scope_key:
        raise PermissionError("authority fence transition scope mismatch")
    with _LOCK:
        if transition_capability.source_fence != _FENCE:
            raise PermissionError("authority fence transition source state stale")
        _FENCE += 1
        return _FENCE


def advance_mandate_source_generation_without_compatibility_for_test() -> str:
    """Advance the authoritative mandate source generation without asserting compatibility.

    Test/reference-harness support only. This proves that compatibility for one
    mandate source generation cannot silently bless a distinct generation.
    """
    global _MANDATE_SOURCE_VERSION, _FENCE
    with _LOCK:
        try:
            prefix, raw = _MANDATE_SOURCE_VERSION.rsplit("-", 1)
            _MANDATE_SOURCE_VERSION = f"{prefix}-{int(raw) + 1:03d}"
        except (ValueError, TypeError):
            _MANDATE_SOURCE_VERSION = f"{_MANDATE_SOURCE_VERSION}-NEXT"
        _FENCE += 1
        return _MANDATE_SOURCE_VERSION

def advance_authority_epoch_for_test() -> str:
    """Advance the synthetic authority epoch without changing mandate economics.

    Test/reference-harness support only. A new authority-state epoch must not,
    by itself, imply replenishment of an aggregate mandate amount.
    """
    global _EPOCH_ID, _FENCE
    with _LOCK:
        try:
            prefix, raw = _EPOCH_ID.rsplit("-", 1)
            _EPOCH_ID = f"{prefix}-{int(raw) + 1:03d}"
        except (ValueError, TypeError):
            _EPOCH_ID = f"{_EPOCH_ID}-NEXT"
        _FENCE += 1
        return _EPOCH_ID


def advance_usage_window_for_test() -> str:
    """Advance the authoritative synthetic NORM-PAY-001 usage window.

    Test/reference-harness support only. This models a competent normative
    window transition separately from generic authority epoch/fence movement.
    """
    global _USAGE_WINDOW_ID, _FENCE
    with _LOCK:
        try:
            prefix, raw = _USAGE_WINDOW_ID.rsplit("-", 1)
            _USAGE_WINDOW_ID = f"{prefix}-{int(raw) + 1:03d}"
        except (ValueError, TypeError):
            _USAGE_WINDOW_ID = f"{_USAGE_WINDOW_ID}-NEXT"
        # Window transition is authority-material state and advances the
        # authoritative fence; it does not alter the generic authority epoch.
        _FENCE += 1
        return _USAGE_WINDOW_ID


def set_usage_window_for_test(
    window_id: str, *, transition_capability: object | None = None
) -> str:
    """Apply a presented synthetic usage-window transition with monotonic validation.

    Test/reference-harness support only. Canonical DAY-NNN window identities may
    move forward, but stale/equal/backward identities cannot replace current
    authoritative usage-window state.
    """
    global _USAGE_WINDOW_ID, _FENCE
    if transition_capability is not _USAGE_WINDOW_TRANSITION_CAPABILITY:
        raise ValueError("authoritative usage window transition required")
    if not window_id:
        raise ValueError("usage window identity required")
    with _LOCK:
        try:
            current_prefix, current_raw = _USAGE_WINDOW_ID.rsplit("-", 1)
            proposed_prefix, proposed_raw = window_id.rsplit("-", 1)
            current_n = int(current_raw)
            proposed_n = int(proposed_raw)
        except (ValueError, TypeError):
            raise ValueError("usage window identity is not comparable")

        if proposed_prefix != current_prefix:
            raise ValueError("usage window domain mismatch")
        if proposed_n <= current_n:
            raise ValueError("usage window transition must be strictly forward")

        _USAGE_WINDOW_ID = window_id
        _FENCE += 1
        return _USAGE_WINDOW_ID


@dataclass(frozen=True)
class AuthorityCompatibilityCut:
    compatibility_cut_id: str
    authority_epoch_id: str
    mandate_source_version: str
    actor_source_version: str
    operational_source_version: str


def get_authority_compatibility_cut(
    mandate_id: str, *, actor_source_version: str, operational_source_version: str
) -> AuthorityCompatibilityCut | None:
    """Return the bounded reference compatibility cut for multi-source authority state.

    This is an explicit compatibility assertion for the reference fixture, not
    an inference from a hash/version vector and not a production consensus
    mechanism.
    """
    snapshot = get_authority_snapshot(mandate_id)
    if snapshot is None:
        return None
    mandate_version = snapshot.mandate_source_version
    # Compatibility is explicit reference state. Source generations do not
    # become mutually compatible merely because they are individually current
    # or can be named in a version vector.
    with _LOCK:
        if (mandate_version, actor_source_version, operational_source_version) not in _COMPATIBLE_SOURCE_GENERATIONS:
            return None
    payload = {
        "authority_epoch_id": snapshot.authority_epoch_id,
        "mandate_source_version": mandate_version,
        "actor_source_version": actor_source_version,
        "operational_source_version": operational_source_version,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return AuthorityCompatibilityCut(
        compatibility_cut_id=f"COMPAT-{hashlib.sha256(raw).hexdigest()}",
        authority_epoch_id=snapshot.authority_epoch_id,
        mandate_source_version=mandate_version,
        actor_source_version=actor_source_version,
        operational_source_version=operational_source_version,
    )


def restore_current_reference_compatibility_for_test(
    *, actor_source_version: str = "1", operational_source_version: str = "1"
) -> None:
    """Restore the canonical reference compatibility cut after a destructive hostile test.

    Test cleanup only. This is not an authority transition mechanism and must
    not be used by production resolution paths.
    """
    snapshot = get_authority_snapshot("MANDATE-TREASURY-001")
    if snapshot is None:
        raise ValueError("authoritative mandate not found")
    with _LOCK:
        _COMPATIBLE_SOURCE_GENERATIONS.add(
            (snapshot.mandate_source_version, actor_source_version, operational_source_version)
        )


def register_authority_compatibility_cut_for_test(
    *,
    actor_source_version: str,
    operational_source_version: str,
    mandate_source_version: str | None = None,
    registration_capability: object | None = None,
) -> None:
    """Establish a bounded reference compatibility relation for source generations.

    Test/reference-harness support only. This models a competent compatibility
    assertion separately from the source versions themselves.
    """
    if registration_capability is not _COMPATIBILITY_CUT_REGISTRATION_CAPABILITY:
        raise ValueError("authoritative compatibility-cut registration required")
    if not actor_source_version or not operational_source_version:
        raise ValueError("source generation identity required")
    with _LOCK:
        effective_mandate_version = mandate_source_version
        if effective_mandate_version is None:
            snapshot = get_authority_snapshot("MANDATE-TREASURY-001")
            if snapshot is None:
                raise ValueError("authoritative mandate not found")
            effective_mandate_version = snapshot.mandate_source_version
        _COMPATIBLE_SOURCE_GENERATIONS.add(
            (effective_mandate_version, actor_source_version, operational_source_version)
        )
