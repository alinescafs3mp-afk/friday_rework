# PUBLIC ANALYSIS-ONLY SNAPSHOT — intentionally UNBOUND.
# Do not import, run, install, or treat placeholders as authority.
# Original-source and exported-source hashes are separate manifest facts.
"""Exact selected existing ordinary atomic primitives; inert API facade only."""
import os
import stat
from pathlib import Path
class _API:
    @staticmethod
    def require(ok, code):
        if not ok: raise ValueError(code)
def api(): return _API

def write(path, data, mode=0o600):
    fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(data); stream.flush(); os.fsync(stream.fileno())

class SourceUpdateDirectories:
    """Hold exact directory descriptors across additive source publication.

    Only declared absent parents may be created. Every operation is relative to
    a held descriptor, so replacing a path with a link cannot redirect a write.
    Named inode checks still refuse any replacement and retain foreign entries.
    """
    def __init__(self, home, files, new_directories):
        f = api(); self.home = home; self.fds = {}; self.identities = {}; self.created = []
        self.new = set(new_directories); self.allowed = {}; self.parents = {}; self.workspace = None
        try:
            for name in set(files) | self.new:
                relative = Path(name)
                f.require(type(name) is str and not relative.is_absolute()
                    and name == relative.as_posix() and name != '.'
                    and not any(p in ('.','..') for p in relative.parts),
                    'ordinary_update_directory_relative_path_required')
            required = {''}
            for name in files:
                child = Path(name)
                while child != Path('.'):
                    parent = str(child.parent) if child.parent != Path('.') else ''
                    self.allowed.setdefault(parent,set()).add(child.name)
                    required.add(parent); child = child.parent
            f.require(self.new <= required and '' not in self.new,
                'ordinary_update_unused_new_directory')
            self.ordered = sorted(required,key=lambda n:(len(Path(n).parts),n))
            for name in self.ordered:
                parent = str(Path(name).parent) if name and Path(name).parent != Path('.') else ''
                self.parents[name] = parent
                if name in self.new:
                    if parent in self.fds:
                        try: os.stat(Path(name).name,dir_fd=self.fds[parent],follow_symlinks=False)
                        except FileNotFoundError: pass
                        else: f.require(False,'ordinary_update_new_directory_exists')
                    else:
                        f.require(parent in self.new,'ordinary_update_new_directory_parent_required')
                    continue
                f.require(not name or parent in self.fds,'ordinary_update_missing_directory')
                fd = (os.open(home,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW) if not name else
                    os.open(Path(name).name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=self.fds[parent]))
                self.fds[name] = fd; self.identities[name] = self.identity(os.fstat(fd))
            self.prove()
        except BaseException:
            self.close(); raise

    @staticmethod
    def identity(info):
        api().require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700,'ordinary_update_private_directory_required')
        return tuple(getattr(info,k) for k in ('st_dev','st_ino','st_uid','st_mode'))

    def prove(self):
        f = api()
        if self.workspace is not None:
            path, fd, identity = self.workspace
            f.require(self.identity(path.lstat()) == self.identity(os.fstat(fd)) == identity,
                'ordinary_update_directory_staging_changed')
        for name in self.ordered:
            parent = self.parents[name]
            if name not in self.fds:
                if parent in self.fds:
                    try: os.stat(Path(name).name,dir_fd=self.fds[parent],follow_symlinks=False)
                    except FileNotFoundError: continue
                    f.require(False,'ordinary_update_new_directory_appeared')
                continue
            named = (self.home.lstat() if not name else
                os.stat(Path(name).name,dir_fd=self.fds[parent],follow_symlinks=False))
            f.require(self.identity(named) == self.identity(os.fstat(self.fds[name])) == self.identities[name],
                'ordinary_update_directory_ownership_changed')
            if name in self.created:
                f.require(set(os.listdir(self.fds[name])) <= self.allowed.get(name,set()),
                    'ordinary_update_directory_inventory_changed')

    def create(self, staging):
        # Establish ownership before a source name is published. The transaction
        # namespace is private and owned, like its existing before/after trees.
        staging.mkdir(mode=0o700)
        fd = os.open(staging,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        self.workspace = (staging,fd,self.identity(os.fstat(fd)))
        self.prove()
        for number,name in enumerate(self.ordered):
            if name not in self.new: continue
            self.prove(); parent_fd = self.fds[self.parents[name]]
            temporary = 'new-'+str(number)
            os.mkdir(temporary,mode=0o700,dir_fd=fd)
            owned_fd = os.open(temporary,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            try:
                identity = self.identity(os.fstat(owned_fd))
                api().require(self.identity(os.stat(temporary,dir_fd=fd,follow_symlinks=False)) == identity,
                    'ordinary_update_directory_staging_changed')
                rename_directory_noreplace(fd,temporary,parent_fd,Path(name).name)
                self.fds[name] = owned_fd; owned_fd = None
                self.identities[name] = identity; self.created.append(name)
                self.prove(); os.fsync(parent_fd); os.fsync(fd)
            finally:
                if owned_fd is not None: os.close(owned_fd)

    def parent_fd(self, name):
        parent = str(Path(name).parent) if Path(name).parent != Path('.') else ''
        return self.fds.get(parent)

    def remove_created(self):
        self.prove()
        if not self.created: return
        staging, staging_fd, _ = self.workspace
        for number,name in enumerate(reversed(self.created[:])):
            self.prove()
            api().require(not os.listdir(self.fds[name]),'ordinary_update_directory_not_empty')
            parent_fd = self.fds[self.parents[name]]; quarantine = 'removed-'+str(number)
            # A concurrent replacement is moved intact, never recursively erased.
            # Verify the moved inode in our private namespace before removing it.
            rename_directory_noreplace(parent_fd,Path(name).name,staging_fd,quarantine)
            info = os.stat(quarantine,dir_fd=staging_fd,follow_symlinks=False)
            moved = tuple(getattr(info,k) for k in ('st_dev','st_ino','st_uid','st_mode'))
            if moved != self.identities[name]:
                # Undo our move if its destination remains absent. NOREPLACE
                # preserves any third-party entry that appeared in the meantime.
                rename_directory_noreplace(staging_fd,quarantine,parent_fd,Path(name).name)
                api().require(False,'ordinary_update_directory_ownership_changed')
            api().require(not os.listdir(self.fds[name]),'ordinary_update_directory_not_empty')
            os.rmdir(quarantine,dir_fd=staging_fd); os.fsync(parent_fd); os.fsync(staging_fd)
            os.close(self.fds.pop(name)); self.identities.pop(name); self.created.remove(name)
            self.prove()

    def close(self):
        if self.workspace is not None:
            os.close(self.workspace[1]); self.workspace = None
        for fd in reversed(list(self.fds.values())): os.close(fd)
        self.fds.clear()

    def __enter__(self): return self
    def __exit__(self,*args): self.close()

def update_file_state_at(path, parent_fd):
    """Read one owned regular file relative to a retained parent descriptor."""
    f = api()
    try: fd = os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=parent_fd)
    except FileNotFoundError: return None
    try:
        first = os.fstat(fd)
        f.require(stat.S_ISREG(first.st_mode) and first.st_uid == os.getuid() and first.st_nlink == 1,
            'ordinary_update_owned_regular_file_required')
        with os.fdopen(fd,'rb',closefd=False) as stream: data = stream.read(64*1024**2+1)
        last = os.fstat(fd); named = os.stat(path.name,dir_fd=parent_fd,follow_symlinks=False)
        keys = ('st_dev','st_ino','st_uid','st_nlink','st_mode','st_size','st_mtime_ns','st_ctime_ns')
        f.require(len(data) <= 64*1024**2 and all(getattr(first,k)==getattr(last,k)==getattr(named,k) for k in keys),
            'ordinary_update_file_identity_changed')
        return {'data':data,'mode':stat.S_IMODE(first.st_mode),
            'identity':tuple(getattr(first,k) for k in ('st_dev','st_ino','st_uid','st_nlink','st_mode'))}
    finally: os.close(fd)

def update_file_state(path, parent_fd=None):
    """Exact bytes and inode custody; absence is never an empty beforeimage."""
    if parent_fd is not None: return update_file_state_at(path,parent_fd)
    f = api()
    if not os.path.lexists(path): return None
    first = path.lstat()
    data = f.owned_file(path)
    last = path.lstat()
    keys = ('st_dev','st_ino','st_uid','st_nlink','st_mode')
    identity = tuple(getattr(first,k) for k in keys)
    f.require(identity == tuple(getattr(last,k) for k in keys), 'ordinary_update_file_identity_changed')
    return {'data':data,'mode':stat.S_IMODE(first.st_mode),'identity':identity}

def same_update_file(path, expected, parent_fd=None):
    return update_file_state(path,parent_fd) == expected

def publish_update_file(path, data, mode, before, owned, name, parent_fd=None):
    """Publish one recorded inode; new files use an exclusive hard-link claim."""
    f = api(); temporary = path.with_name(path.name+'.ordinary-staged')
    target = path if parent_fd is None else path.name
    stage = temporary if parent_fd is None else temporary.name
    def present():
        try: os.stat(stage,dir_fd=parent_fd,follow_symlinks=False); return True
        except FileNotFoundError: return False
    try:
        fd = os.open(stage,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode,dir_fd=parent_fd)
    except FileExistsError as exc:
        from scripts.dsh_prepare import StopUnconfirmed
        raise StopUnconfirmed('ordinary update staging path ownership requires reconciliation') from exc
    created = None
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'wb',closefd=False) as stream:
            stream.write(data);stream.flush();os.fsync(fd)
        st = os.fstat(fd)
        created = {'data':data,'mode':mode,'identity':tuple(getattr(st,k) for k in
            ('st_dev','st_ino','st_uid','st_nlink','st_mode'))}
        f.require(same_update_file(path,before,parent_fd),'ordinary_update_publication_identity_changed')
        f.require(same_update_file(temporary,created,parent_fd),'ordinary_update_staging_identity_changed')
        owned[name] = created
        if before is None:
            os.link(stage,target,src_dir_fd=parent_fd,dst_dir_fd=parent_fd,follow_symlinks=False)
            # owned_file intentionally rejects hard links; here both names
            # must still identify exactly our descriptor before unlinking one.
            linked = tuple(2 if i == 3 else value for i,value in enumerate(created['identity']))
            for candidate in (temporary,path):
                info=os.stat(candidate if parent_fd is None else candidate.name,dir_fd=parent_fd,follow_symlinks=False)
                f.require(tuple(getattr(info,k) for k in ('st_dev','st_ino','st_uid','st_nlink','st_mode'))
                    == linked,'ordinary_update_link_identity_changed')
            os.unlink(stage,dir_fd=parent_fd)
        else:
            os.replace(stage,target,src_dir_fd=parent_fd,dst_dir_fd=parent_fd)
        f.require(same_update_file(path,created,parent_fd),'ordinary_update_published_identity_changed')
        if parent_fd is None: sync_directory(path.parent)
        else: os.fsync(parent_fd)
    finally:
        os.close(fd)
        if present():
            # If publication failed, only our own exact staging inode is removed.
            if created is None or not same_update_file(temporary,created,parent_fd):
                from scripts.dsh_prepare import StopUnconfirmed
                raise StopUnconfirmed('ordinary update staging ownership requires reconciliation')
            os.unlink(stage,dir_fd=parent_fd)
