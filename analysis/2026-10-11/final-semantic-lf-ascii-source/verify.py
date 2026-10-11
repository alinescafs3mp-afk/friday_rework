import argparse,hashlib,json,pathlib,sys
def require(x,s):
 if not x:raise RuntimeError(s)
def main():
 require(__debug__,"optimized Python refused")
 a=argparse.ArgumentParser();a.add_argument("--manifest-sha256",required=True);args=a.parse_args();p=pathlib.Path(__file__).resolve().parent;m=p/"MANIFEST.json"
 require(hashlib.sha256(m.read_bytes()).hexdigest()==args.manifest_sha256,"external manifest mismatch")
 j=json.loads(m.read_bytes());rows=j["files"];expected={"MANIFEST.json"}|{r["path"] for r in rows}
 require(len(rows)==6 and len(expected)==7,"composition count")
 actual={str(f.relative_to(p)) for f in p.rglob("*") if f.is_file()};require(actual==expected,"different file composition")
 for r in rows:
  f=p/r["path"];require(not f.is_symlink() and f.is_file(),"nonregular payload");raw=f.read_bytes();require(len(raw)==r["bytes"] and hashlib.sha256(raw).hexdigest()==r["sha256"],"payload drift")
 s=json.loads((p/"STATUS.json").read_bytes())
 for k in ("runtime_admission","release_accepted","daily_checkpoint_complete"):require(s[k] is False,"status promotion")
 require(j["runtime_admission"] is False,"manifest promotion")
 print(json.dumps({"files":7,"payloads":6,"source_files":2,"source_integrity":True,"runtime_admission":False,"source_execution":False}))
if __name__=="__main__":main()
