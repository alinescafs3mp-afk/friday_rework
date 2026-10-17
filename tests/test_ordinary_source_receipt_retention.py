"""Opaque synthetic Telegram receipt retention; no account/runtime effects."""
import os
from pathlib import Path
import pytest
from scripts import friday_ordinary_install as o
from scripts import friday_install as f
from scripts.install_containment import Budget
from test_ordinary_dsh_project_update import put

@pytest.fixture
def receipts(tmp_path,monkeypatch):
 home=tmp_path/'home';home.mkdir(mode=0o700)
 for name in o.EXACT_RESPONSE_BINDING_FILES:put(home/name,b'synthetic retained renderer reference\n')
 for account in ('1001','2002'):put(home/f'telegram_update_receipts_{account}.json',b'{"synthetic":"opaque receipt"}\n')
 monkeypatch.setattr(o,'checked_source82_retained',lambda *args:None)
 names,dirs=o.source88_retained_inventory(home,Budget(30))
 request={'retained_data_directories':dirs,'retained_data_files':{n:{'path':str(home/n),'sha256':f.digest((home/n).read_bytes()),'mode':0o600} for n in names}}
 return home,request

def test_all_direct_account_receipts_retained_without_embedding_identifiers(receipts):
 home,request=receipts;before={p.name:o.update_file_state(p) for p in home.iterdir()}
 o.checked_source88_retained(home,request,Budget(30))
 assert {'telegram_update_receipts_1001.json','telegram_update_receipts_2002.json'} <= set(request['retained_data_files'])
 assert all(o.update_file_state(home/n)==v for n,v in before.items())

@pytest.mark.parametrize('fault',['omitted','new_receipt','changed','mode','symlink','directory'])
def test_receipt_drift_and_nonregular_files_refused(receipts,fault):
 home,request=receipts;name='telegram_update_receipts_1001.json';path=home/name
 if fault=='omitted':request['retained_data_files'].pop(name)
 elif fault=='new_receipt':put(home/'telegram_update_receipts_3003.json',b'new opaque receipt\n')
 elif fault=='changed':put(path,b'foreign bytes\n')
 elif fault=='mode':path.chmod(0o644)
 elif fault=='symlink':path.unlink();path.symlink_to(home/'telegram_update_receipts_2002.json')
 elif fault=='directory':path.unlink();path.mkdir(mode=0o700)
 with pytest.raises(ValueError):o.checked_source88_retained(home,request,Budget(30))

def test_receipt_resource_limit_remains_closed(receipts,monkeypatch):
 home,request=receipts
 monkeypatch.setattr(o,'EXACT_RESPONSE_RETAINED_MAX_FILES',len(request['retained_data_files']))
 with pytest.raises(ValueError,match='retained_resource_limit'):o.source88_retained_inventory(home,Budget(30))

def test_root_receipt_namespace_is_direct_and_closed(receipts):
 home,request=receipts;put(home/'telegram_update_receipts_ignored.txt',b'outside JSON receipt namespace\n')
 assert o.source88_retained_inventory(home,Budget(30))[0]==set(request['retained_data_files'])
