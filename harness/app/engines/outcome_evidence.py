from __future__ import annotations

"""Bounded reference model for post-commit outcome-evidence competence.

Evidence competence is established by this module's registry, not by caller-
controlled identifier syntax. This is still a process-local reference harness
and does not claim production external attestation, IAM, KMS/HSM, or durable
cross-system provenance.
"""

from dataclasses import dataclass
from threading import RLock


@dataclass(frozen=True)
class CompetentOutcomeEvidence:
    evidence_id: str
    permit_signature: str
    action_binding_hash: str
    outcome: str
    authoritative_source_id: str
    source_competence_id: str
    finality_state: str = "FINAL"
    supersedes_evidence_ids: tuple[str, ...] = ()


_LOCK = RLock()
_EVIDENCE: dict[str, CompetentOutcomeEvidence] = {}
# Exact executions whose evidence set has already been relied upon for an
# irreversible authority-usage disposition.  This closes disposition, not
# observation: later evidence may still be preserved.
_DISPOSED_OUTCOMES: dict[tuple[str, str], str] = {}
_ALLOWED_SOURCES = {
    ("REFERENCE-CONSEQUENCE-OBSERVER-001", "REFERENCE-OUTCOME-COMPETENCE-ROOT-001"),
}


def register_competent_outcome_evidence(evidence: CompetentOutcomeEvidence) -> None:
    if (evidence.authoritative_source_id, evidence.source_competence_id) not in _ALLOWED_SOURCES:
        raise ValueError("outcome evidence source is not competent")
    if evidence.outcome not in ("FORMATION", "NON_FORMATION"):
        raise ValueError("unsupported outcome evidence")
    if evidence.finality_state not in ("PROVISIONAL", "FINAL"):
        raise ValueError("unsupported outcome evidence finality")
    with _LOCK:
        for predecessor_id in evidence.supersedes_evidence_ids:
            predecessor = _EVIDENCE.get(predecessor_id)
            if predecessor is None:
                raise ValueError("superseded outcome evidence is unknown")
            if predecessor.permit_signature != evidence.permit_signature or predecessor.action_binding_hash != evidence.action_binding_hash:
                raise ValueError("supersession must remain within the exact execution")
            if predecessor.finality_state != "PROVISIONAL":
                raise ValueError("only provisional outcome evidence may be superseded")
        if evidence.supersedes_evidence_ids and evidence.finality_state != "FINAL":
            raise ValueError("only final outcome evidence may supersede prior observations")

        existing = _EVIDENCE.get(evidence.evidence_id)
        if existing is not None and existing != evidence:
            raise ValueError("outcome evidence identity already bound differently")
        _EVIDENCE[evidence.evidence_id] = evidence


def verify_competent_outcome_evidence(
    evidence_ids: tuple[str, ...],
    *,
    permit_signature: str,
    action_binding_hash: str,
    outcome: str,
) -> bool:
    if not evidence_ids:
        return False
    with _LOCK:
        observed = [
            evidence for evidence in _EVIDENCE.values()
            if evidence.permit_signature == permit_signature
            and evidence.action_binding_hash == action_binding_hash
        ]
        if not observed:
            return False

        # Unresolved-source observations cannot establish an outcome. They
        # preserve uncertainty only when their asserted outcome materially
        # conflicts with the competent outcome being resolved; agreeing
        # untrusted noise must not gain veto power.
        unresolved_source = [
            evidence for evidence in observed
            if (evidence.authoritative_source_id, evidence.source_competence_id) not in _ALLOWED_SOURCES
        ]
        if any(evidence.outcome != outcome for evidence in unresolved_source):
            return False

        applicable = [
            evidence for evidence in observed
            if (evidence.authoritative_source_id, evidence.source_competence_id) in _ALLOWED_SOURCES
        ]
        if not applicable:
            return False

        # A FINAL observation may resolve an already-disagreeing provisional
        # evidence set only by explicitly superseding the whole active
        # provisional set for that exact execution.  Selective pruning must
        # not manufacture apparent coherence.
        provisional = [e for e in applicable if e.finality_state == "PROVISIONAL"]
        provisional_outcomes = {e.outcome for e in provisional}
        if len(provisional_outcomes) > 1:
            provisional_ids = {e.evidence_id for e in provisional}
            for final_evidence in (e for e in applicable if e.finality_state == "FINAL" and e.supersedes_evidence_ids):
                claimed = set(final_evidence.supersedes_evidence_ids)
                if claimed & provisional_ids and claimed != provisional_ids:
                    return False

        superseded_ids = {
            predecessor_id
            for evidence in applicable
            if evidence.finality_state == "FINAL"
            for predecessor_id in evidence.supersedes_evidence_ids
        }
        applicable = [evidence for evidence in applicable if evidence.evidence_id not in superseded_ids]
        if not applicable:
            return False

        # Resolution cannot be obtained by selecting only the favourable member
        # of a disagreeing competent, non-superseded evidence set.
        applicable_outcomes = {evidence.outcome for evidence in applicable}
        if len(applicable_outcomes) != 1 or outcome not in applicable_outcomes:
            return False

        for evidence_id in evidence_ids:
            evidence = _EVIDENCE.get(evidence_id)
            if evidence is None or evidence not in applicable or evidence.outcome != outcome:
                return False
        return True


def close_outcome_disposition(
    *,
    permit_signature: str,
    action_binding_hash: str,
    outcome: str,
) -> None:
    """Record the outcome direction relied upon for irreversible usage disposition."""
    if outcome not in ("FORMATION", "NON_FORMATION"):
        raise ValueError("unsupported disposed outcome")
    key = (permit_signature, action_binding_hash)
    with _LOCK:
        existing = _DISPOSED_OUTCOMES.get(key)
        if existing is not None and existing != outcome:
            raise ValueError("exact execution disposition already closed to opposite outcome")
        _DISPOSED_OUTCOMES[key] = outcome


def get_closed_outcome_disposition(*, permit_signature: str, action_binding_hash: str) -> str | None:
    with _LOCK:
        return _DISPOSED_OUTCOMES.get((permit_signature, action_binding_hash))
