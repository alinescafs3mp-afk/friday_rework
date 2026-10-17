"""Pure renderer input-delta controls; runtime renderer admission is separate."""
import copy
import pytest
from scripts import friday_ordinary_install as o

@pytest.fixture
def renderer_delta(monkeypatch):
 old={'inference':{'key_env':'FRIDAY_LLM_API_KEY','model':'synthetic-primary'},
      'compression_inference':{'key_env':'FRIDAY_COMPRESSION_API_KEY','model':'synthetic-compressor'},
      'compression_multipass':{'enabled':True,'max_calls':64},'runtime':{'enabled':False},
      'original_budget':{'expired':True},'reasoning':'retained'}
 new=copy.deepcopy(old)
 new['compression_inference']['exact_renderer']={'binding':{'path':'/synthetic/binding','sha256':'a'*64},'deployment':{'path':'/synthetic/deployment','sha256':'b'*64}}
 seen=[]
 def references(product):seen.append(copy.deepcopy(product));return ('synthetic-binding','synthetic-deployment')
 monkeypatch.setattr(o,'inference_renderer_references',references)
 return old,new,seen

def test_only_compressor_exact_renderer_leaf_can_be_added(renderer_delta):
 old,new,seen=renderer_delta;before=copy.deepcopy((old,new))
 assert o.inference_renderer_delta(old,new)==('synthetic-binding','synthetic-deployment')
 assert seen==[new] and (old,new)==before

@pytest.mark.parametrize('fault',['primary_model','compressor_model','primary_key','compressor_key','runtime_zero','runtime_true','runtime_extra','multipass','budget','reasoning','primary_renderer','missing_leaf','already_bound','new_field'])
def test_renderer_delta_refuses_operational_and_typed_changes(renderer_delta,fault):
 old,new,seen=renderer_delta
 if fault=='primary_model':new['inference']['model']='changed'
 elif fault=='compressor_model':new['compression_inference']['model']='changed'
 elif fault=='primary_key':old['inference']['key_env']=new['inference']['key_env']='changed'
 elif fault=='compressor_key':old['compression_inference']['key_env']=new['compression_inference']['key_env']='changed'
 elif fault=='runtime_zero':new['runtime']['enabled']=0
 elif fault=='runtime_true':new['runtime']['enabled']=True
 elif fault=='runtime_extra':new['runtime']['extra']=False
 elif fault=='multipass':new['compression_multipass']['max_calls']=65
 elif fault=='budget':new['original_budget']['expired']=False
 elif fault=='reasoning':new['reasoning']='changed'
 elif fault=='primary_renderer':new['inference']['exact_renderer']=copy.deepcopy(new['compression_inference']['exact_renderer'])
 elif fault=='missing_leaf':new['compression_inference'].pop('exact_renderer')
 elif fault=='already_bound':old['compression_inference']['exact_renderer']=copy.deepcopy(new['compression_inference']['exact_renderer'])
 elif fault=='new_field':new['new_field']=True
 with pytest.raises(ValueError):o.inference_renderer_delta(old,new)
 assert not seen
