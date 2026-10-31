# Minimal preparation-lifetime source delta

NONEXECUTABLE PUBLICATION TRANSCRIPT. Incomplete line-numbered fragments only: no module, imports, complete callable, runnable test, private input or execution recipe. No selected token below is changed. Private binding paths and all request/response material are omitted. These fragments describe the source-only repair accepted by Root; they are not an installed artifact.

The repaired preparation leaf has SHA-256 `94df2b2802b799e0ed09dc9111dc17691c90b555faf07762fbf8b15d10556108`. The repaired entry leaf has SHA-256 `230f1c7fa8b7ef56e56131ea300f523824e4a9ff9a67c49ce5596e3ae1f34baf`. Its only change binds the exact new preparation leaf; all entry logic is otherwise AST-identical. Against the accepted twelve-leaf source graph, only these two leaves change; the accepted comparison records ten unchanged leaves. The full private patch is identified by SHA-256 `50503411b857d879a255ec354198e404228c46976f785647629490320fa67935`.

The previous captured reader checked the preparation budget unconditionally before and after the underlying read. The repaired reader checks it only while the preparation reader scope is active. The underlying read is still called in both states.

```text
00010 |         self._reader_scope_active=True
[unrelated source omitted]
00028 |                 if self._reader_scope_active:self.check()
00029 |                 value=_original(*a,**kw)
00030 |                 if self._reader_scope_active:self.check()
00031 |                 return value
```

The helper context refuses reentry after closure. A final preparation check is required before normal handoff; an exhausted wall or CPU budget still prevents handoff. The finally block ends the reader constraint and restores the existing process resource and subprocess settings on every scope exit. Scope closure does not make an explicit preparation-budget check valid again.

```text
00035 |         if not self._reader_scope_active:raise RuntimeError('S03_preparation_scope_already_closed')
[unrelated source omitted]
00071 |         try:
00072 |             self.check();yield self;self.check()
00073 |         finally:
[explanatory source comments omitted]
00077 |             self._reader_scope_active=False
00078 |             subprocess.run=original
00079 |             resource.setrlimit(resource.RLIMIT_CPU,old_cpu)
00080 |             signal.signal(signal.SIGXCPU,old_sig)
00081 |             resource.setrlimit(resource.RLIMIT_AS,old_as)
00082 |             os.sched_setaffinity(0,affinity)
```

The four typed JSON joins, all finite budget declarations, original runtime/cleanup clocks, once-only protections and canonical tester remain unchanged. The canonical tester SHA-256 is `b218e83246dab09f90d75597477c0bf73cc0f94438b05c98a595e11cc1d6a1c5`.

This narrow delta does not resolve every possible exception-masking mechanism: an existing helper's final preparation check can still replace an earlier helper exception if its budget expires. That separate mechanism was not demonstrated as the first cause of the actual observation failure. The accepted lifetime repair neither repairs the partial historical capture nor authorizes another effect.
