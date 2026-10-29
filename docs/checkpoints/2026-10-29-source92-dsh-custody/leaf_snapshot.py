"""Exact Source92 analysis excerpt for an already authenticated namespace.

The caller supplies ns['protected_parent'] and ns['identity'] from its existing
verified namespace. This module neither authenticates that namespace nor creates
product authority. It is not a replacement runtime or an installation recipe.
"""
import os
from pathlib import Path
import stat

def leaf_snapshot(ns,workspace):
    result={}
    for base,dirs,files in os.walk(workspace,followlinks=False):
        # Current source directories are access boundaries too. Hold each
        # no-follow parent chain while measuring its own leaf entries; leaf
        # identities alone cannot detect chmod/chown of an unchanged parent.
        with ns['protected_parent'](Path(base)) as (fd,_):
            dirs[:]=sorted(d for d in dirs if d not in {'.git','.venv','venv','node_modules','__pycache__'} and not d.endswith('.egg-info'))
            links=[name for name in dirs if stat.S_ISLNK(os.stat(name,dir_fd=fd,follow_symlinks=False).st_mode)]
            for name in [*files,*links]:
                if name.endswith('.egg-info'):continue
                path=Path(base)/name;row=ns['identity'](os.stat(name,dir_fd=fd,follow_symlinks=False))
                if stat.S_ISLNK(row['st_mode']):row['link_target']=os.readlink(name,dir_fd=fd)
                result[path.relative_to(workspace).as_posix()]=row
    return result
