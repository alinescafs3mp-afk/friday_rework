import fcntl,json,os
from pathlib import Path
def perform(p,s):
 d=json.loads(Path(p).read_bytes())
 if d["case"]=="worker_flock":
  mark=os.open(d["phase"],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400)
  os.write(mark,b"BEFORE_PHYSICAL_FLOCK");os.fsync(mark);os.close(mark)
  fd=os.open(d["lock"],os.O_RDONLY);fcntl.flock(fd,fcntl.LOCK_EX)
  raise RuntimeError("fixture lock unexpectedly released")
 fd=os.open(d["marker"],os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400)
 os.write(fd,b"REAL_FIXTURE_ENTRY_RETURN");os.fsync(fd);os.close(fd)
 return {"isolated_fixture":True}
