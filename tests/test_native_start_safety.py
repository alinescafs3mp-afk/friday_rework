"""Expected-safety regressions: failures are retained product findings, no live effects."""
import json,os,datetime
import pytest
from scripts import friday_start as start
from scripts.install_containment import Budget
from scripts.dsh_prepare import StopUnconfirmed
pytest_plugins=['test_native_product_start']

@pytest.mark.parametrize('fault',['stale-heartbeat','wrong-incarnation','wrong-home','wrong-code'])
def test_gateway_observation_must_reject_inconsistent_runtime_record(native_home,monkeypatch,fault):
 from test_native_product_start import observe
 f=native_home;actual_read=f.gw._read_gateway_runtime_status
 monkeypatch.setenv("HERMES_HOME",str(f.home))
 observe(f,monkeypatch)
 monkeypatch.setattr(f.gw,'_read_gateway_runtime_status',actual_read)
 record={'pid':f.record.pid,'kind':'hermes-gateway','start_time':f.record.start_time,'hermes_home':str(f.home),'gateway_state':'running','updated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'code_sha':'781334eea4b9225a3e194faf0c241d9afe218634'}
 if fault=='stale-heartbeat':record['updated_at']='2000-01-01T00:00:00+00:00'
 elif fault=='wrong-incarnation':record['start_time']=f.record.start_time-1
 elif fault=='wrong-home':record['hermes_home']='/synthetic-foreign-home'
 elif fault=='wrong-code':record['code_sha']='0'*40
 p=f.home/'gateway_state.json';p.write_text(json.dumps(record));p.chmod(0o600)
 # Real native reader loads the exact contradictory record, process and service
 # liveness observations are synthetic. No systemctl/process inspection is run.
 assert actual_read()==record
 with pytest.raises(ValueError):start.gateway_observation(f.home,Budget(30))


def test_interrupt_after_gateway_start_must_retain_typed_unknown_stop(launch_fixture,monkeypatch):
 f=launch_fixture
 def interrupt(*args):raise KeyboardInterrupt('synthetic operator interrupt at foreground handoff')
 monkeypatch.setattr(os,'execve',interrupt)
 try:
  start.launch(f.value,f.budget,pins=f.pins)
 except BaseException as exc:
  assert any(isinstance(c,list) and 'start' in c for c in f.calls)
  assert isinstance(exc,StopUnconfirmed),f'Gateway has started but exception is {type(exc).__name__}, not STOP_UNCONFIRMED'
 else:pytest.fail('Unexpected return')

@pytest.mark.parametrize('broken',['missing','malformed','nested-type'])
def test_admin_health_must_report_broken_profile_without_hiding_other_workers(env,broken):
 from hermes_cli.config import load_config_readonly
 load_config_readonly()
 p=env.satellite/'config.yaml'
 if broken=='missing':p.unlink()
 elif broken=='malformed':p.write_text('broken: [')
 else:p.write_text('plugins: []')
 # Native admin policy/owned scope and parser remain real; only temporary files.
 report=env.admin.health()
 assert len(report['workers'])==2
 assert report['runtime_ready'] is False
 assert all(row['deployment_verified'] is False for row in report['workers'])
 assert {row['profile'] for row in report['workers']}=={'default','satellite'}
