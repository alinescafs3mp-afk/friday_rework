"""Additional source-only host input regression. No native effects."""
import json
import pytest
from test_host_native import setup,isolated,native,offline_boundary,ingress,invoke,settle

@pytest.mark.asyncio
async def test_original_received_content_positive(setup,monkeypatch):
    proof=await ingress(setup,file=True)
    original=setup.module.stage_inputs
    def checked(**kw):
        try:return original(**kw)
        except Exception as exc:raise AssertionError('STAGING_DIAGNOSTIC:'+str(exc)) from exc
    monkeypatch.setattr(setup.module,'stage_inputs',checked)
    value=invoke(setup,proof)
    assert value['accepted'],value
    await settle(setup)
