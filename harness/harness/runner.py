from __future__ import annotations
import argparse, json
from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from app.engines.financial_runtime import evaluate_financial
from app.engines.financial_types import FinancialAuthorityRequest


def _dt(v: str) -> datetime:
    return datetime.fromisoformat(v.replace("Z", "+00:00"))


def _rebase(dt: datetime, delta):
    return dt + delta


def load_scenario(path: Path, *, rebase_to_now: bool = True) -> FinancialAuthorityRequest:
    """Load a scenario while preserving its relative temporal relationships.

    Public scenario JSON files are deterministic fixtures with fixed historical
    timestamps. For normal/live harness execution those fixture times are
    rebased so the scenario's requested execution time is current while all
    relative intervals (screening age, mandate expiry relationship, etc.) remain
    unchanged.

    Tests that need the literal historical fixture clock may pass
    ``rebase_to_now=False`` and explicitly control ``sealed_at``.
    """
    d = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
    a = d["authority_request"]
    actor, principal, mandate = a["actor"], a["principal"], a["mandate"]
    pa, ctx = a["proposed_action"], a["runtime_context"]
    scr = a["trusted_evidence"]["sanctions_screening"]

    requested_execution_time = _dt(a["requested_execution_time"])
    mandate_valid_until = _dt(mandate["valid_until"])
    screening_captured_at = _dt(scr["captured_at"])

    if rebase_to_now:
        anchor = datetime.now(timezone.utc)
        delta = anchor - requested_execution_time
        requested_execution_time = anchor
        mandate_valid_until = _rebase(mandate_valid_until, delta)
        screening_captured_at = _rebase(screening_captured_at, delta)

    return FinancialAuthorityRequest(
        scenario_id=d["scenario_id"], action=a["action"], target=a["target"],
        actor_id=actor["id"], actor_type=actor["type"], actor_role=actor["role"],
        actor_authenticated=actor["authenticated"], kya_status=actor["kya_status"],
        principal_id=principal["id"], principal_name=principal["name"],
        mandate_id=mandate["id"], mandate_status=mandate["status"],
        mandate_max_amount=Decimal(str(mandate["max_amount"])), mandate_currency=mandate["currency"],
        permitted_source_accounts=list(mandate["source_accounts"]),
        permitted_counterparty_class=mandate["counterparty_class"],
        mandate_valid_until=mandate_valid_until,
        amount=Decimal(str(pa["amount"])), currency=pa["currency"], source_account=pa["source_account"],
        beneficiary=pa["beneficiary"], beneficiary_account_reference=pa["beneficiary_account_reference"], purpose=pa["purpose"],
        counterparty_status=ctx["counterparty_status"], account_status=ctx["account_status"],
        risk_state=ctx["risk_state"], approval_required=bool(ctx["approval_required"]),
        screening_status=scr["status"], screening_captured_at=screening_captured_at,
        screening_max_age_seconds=int(scr["max_age_seconds"]), screening_source=scr["source"],
        requested_execution_time=requested_execution_time,
        institutional_operation_id=a.get("institutional_operation_id") or f"{d['scenario_id']}:institutional-operation",
    )


def _ser(obj):
    d = asdict(obj)
    def conv(v):
        if isinstance(v, datetime): return v.isoformat()
        if isinstance(v, Decimal): return format(v, ".2f")
        if isinstance(v, list): return [conv(x) for x in v]
        if isinstance(v, dict): return {k: conv(x) for k, x in v.items()}
        return v
    return conv(d)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("scenario", type=Path)
    p.add_argument("--receipt-out", type=Path)
    args = p.parse_args()
    req = load_scenario(args.scenario)
    response, receipt = evaluate_financial(req)
    payload = {"execution_response": _ser(response), "authority_receipt": _ser(receipt)}
    print(json.dumps(payload, indent=2))
    if args.receipt_out:
        args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
        args.receipt_out.write_text(json.dumps(_ser(receipt), indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
