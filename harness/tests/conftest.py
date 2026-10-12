import pytest

from app.engines import institutional_authority as authority
from app.engines import authority_evidence_adapters as adapters


@pytest.fixture(autouse=True)
def isolate_authoritative_reference_state():
    """Isolate reference-model authority state between tests.

    Preserve within-test transitions and restore in-memory state
    after each independent test. Does not reset SQLite evidence.
    """

    with authority._LOCK:
        original_authority = {
            "epoch": authority._EPOCH_ID,
            "usage_window": authority._USAGE_WINDOW_ID,
            "semantics": authority._SEMANTICS,
            "fence": authority._FENCE,
            "mandate_source_version": authority._MANDATE_SOURCE_VERSION,
            "mandates": dict(authority._MANDATES),
            "compatible_generations": set(
                authority._COMPATIBLE_SOURCE_GENERATIONS
            ),
        }

    with adapters._LOCK:
        original_actors = dict(adapters._ACTORS)
        original_operational = dict(adapters._OPERATIONAL)

    try:
        yield
    finally:
        with adapters._LOCK:
            adapters._ACTORS.clear()
            adapters._ACTORS.update(original_actors)
            adapters._OPERATIONAL.clear()
            adapters._OPERATIONAL.update(original_operational)

        with authority._LOCK:
            authority._EPOCH_ID = original_authority["epoch"]
            authority._USAGE_WINDOW_ID = original_authority["usage_window"]
            authority._SEMANTICS = original_authority["semantics"]
            authority._FENCE = original_authority["fence"]
            authority._MANDATE_SOURCE_VERSION = original_authority[
                "mandate_source_version"
            ]
            authority._MANDATES.clear()
            authority._MANDATES.update(original_authority["mandates"])
            authority._COMPATIBLE_SOURCE_GENERATIONS.clear()
            authority._COMPATIBLE_SOURCE_GENERATIONS.update(
                original_authority["compatible_generations"]
            )
