# Durable worker stage observations — source checkpoint

After a DSH safety, A0, or DSH observer returns, the qualification path now writes its complete observation to the existing private attempt directory before Budget.call performs its post-call deadline check or a subsequent stage begins. A later failure can therefore retain the completed stage result. The files use the existing exclusive no-follow, private-mode and fsync writer; original attempt, preparation, user binding and generation remain attached.

These partial files are observations only. They grant no per-job authority and do not replace the full qualification proof, cleanup, current admission, cancellation or deadline checks. An observer that does not return is not reported as complete.

This checkpoint contains the accepted source delta only. Source93 plus this change was not installed at publication preparation; the running installation was Source92. Real new qualification and both ordinary Telegram worker tasks remained incomplete. The earlier failed qualification and its unknown primary cause remain recorded; this change does not establish that cause.

The existing source and receiving reviews reported no open HIGH or MEDIUM findings; their unchanged evidence is reused. Publication checks applied and reversed this exact patch with zero fuzz and full-file byte equality, and parsed the resulting Python without importing the product. No installation, worker, model or user task was performed for this publication.

Apply only to the exact before hash in MANIFEST.json in a disposable source copy using `patch --batch --fuzz=0 -p1`; verify the complete after hash. Reverse with the same command plus `--reverse`. This packet grants no execution authority and is not an installer.
