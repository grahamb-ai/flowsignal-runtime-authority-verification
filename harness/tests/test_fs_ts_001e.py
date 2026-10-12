from pathlib import Path

def test_fs_ts_001e_inactive_mandate_control_is_present():
    """Structural companion to the executable FS-TS-001D regression.

    This checks the candidate's rejection contract, not runtime behaviour.
    """
    source = (
        Path(__file__).parents[1]
        / "app" / "engines" / "protected_consequence.py"
    ).read_text(encoding="utf-8")

    assert 'current_snapshot.mandate.status != "ACTIVE"' in source
    assert 'return "DENIED_MANDATE_NOT_ACTIVE"' in source
