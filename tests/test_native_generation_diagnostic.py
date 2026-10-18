"""An identify failure preserves exact refusal and exposes fixed fields only."""
import pytest

from scripts import friday_start as start, friday_install as install
from scripts.install_containment import Budget

pytest_plugins = ["test_native_product_start"]


def test_unknown_response_has_safe_diagnostic_and_keeps_five_second_bound(native_home, monkeypatch):
    from gateway import control_socket
    from test_native_product_start import observe
    observe(native_home, monkeypatch)
    calls = []

    def identify(home, *, timeout, diagnostic=None):
        calls.append((home, timeout))
        diagnostic.update(transport="unix", outcome="native_error", refusal="source_or_owner_unproved",
                          private="SECRET", mismatch="SECRET")
        return None

    monkeypatch.setattr(control_socket, "identify_gateway", identify)
    with pytest.raises(install.Refused, match="native_gateway_generation_unproved") as caught:
        start.gateway_observation(native_home.home, Budget(30))
    diagnostic = install.safe_diagnostic(caught.value, "ordinary_gateway_observation")
    assert diagnostic["reason"] == "native_gateway_generation_unproved"
    assert diagnostic["identity"] == {"transport": "unix", "outcome": "native_error",
        "refusal": "source_or_owner_unproved", "mismatch": ["response", "protocol", "kind",
        "pid", "start_time", "hermes_home", "code_sha", "friday_owner"]}
    assert "SECRET" not in str(diagnostic) + install.diagnostic_text(diagnostic)
    assert len(calls) == 1 and 0 < calls[0][1] <= 5


def test_untrusted_observation_members_are_discarded():
    exc = install.Refused("native_gateway_generation_unproved")
    exc.friday_identity_observation = {"transport": "SECRET", "outcome": "SECRET",
        "refusal": "SECRET", "mismatch": ["SECRET"], "payload": "SECRET"}
    assert install.safe_diagnostic(exc, "ordinary_gateway_observation")["identity"] == {}
