"""FS-RAW-DENIAL-001 first-red assertion for the bounded two-adapter model.

This intentionally fails: the unmediated example adapter is not governed
by the FlowSignal gateway. It must not be described as a production exploit.
"""
def test_all_configured_adapters_should_require_the_same_authority():
    model_observations = {
        "gateway_refused_operation": True,
        "unmediated_example_adapter_recorded_operation": True,
    }
    assert model_observations["gateway_refused_operation"]
    assert not model_observations["unmediated_example_adapter_recorded_operation"], (
        "UNMET INTEGRATION REQUIREMENT: example route did not share the "
        "gateway's refusal. No actual external consequence was formed."
    )
