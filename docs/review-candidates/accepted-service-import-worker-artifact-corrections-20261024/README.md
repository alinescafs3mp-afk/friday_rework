# Accepted service-import and worker-artifact source corrections

Two exact, previously reviewed source patches, with complete before/after pins in `MANIFEST.json` and publication-file checksums in `SHA256SUMS`.

`registration-service-import.patch` changes one embedding-branch import in `scripts/friday_ordinary_a0_registration.py` to the existing private install-validation namespace. The four imported symbols, embedding validation and source-pin checks are unchanged. The source loader, native plugin namespace and product `sys.path` are unchanged.

The import failure was positively reproduced in a fresh read-only installed service context. Five isolated clean-process source cases separately covered failure before the change, the corrected import, and rejection of a changed pin, a missing pin and an unallowed helper. The corrected-import case also rejected malformed embedding and secondary-source inputs. Independent static delta review found no blocking findings. The earlier opaque HTTP 503 remains **UNKNOWN**; this later identified import cause is not attributed to it.

`external-tester-worker-artifacts.patch` targets the separately maintained `bot_tester.py`. It adds opt-in ordinary worker artifact capture: DSH returns ZIP; A0 returns `result.txt` as `text/plain`. Capture requires the current numeric reply ID, exact filename/MIME and one of eight supported service status captions, with existing route, reply-window, input-freshness and byte-custody guards. Legacy nonce-caption behavior remains supported. Captions are transport metadata and the resulting artifact receipt stays **UNGRADED**; semantic acceptance is separate.

Accepted tester evidence is reported in its original groups, without summing overlapping coverage:

| Evidence group | Accepted count | Scope |
| --- | ---: | --- |
| Author focused controls | 52 | Source-isolated synthetic fixtures; documented callbacks stubbed |
| Author admission controls | 22 | Source-isolated synthetic admission fixtures |
| Packet consumer compatibility | 2 | Source compatibility checks |
| Packet consistency | 26 assertions, 46 references | Packet/source consistency |
| Independent delta review | 68 checks | Source-only; zero new HIGH/MEDIUM findings |
| Exact patch application | 1 | Temporary copy, zero fuzz/offset, exact resulting bytes |

The registration patch has five process cases plus static review; these are separate from the tester counts. This publication reuses accepted observations and adds no execution or test campaign.

This package records source behavior and narrow source controls. Installation, runtime, actual worker execution, Telegram artifact delivery, follow-up behavior and semantic user acceptance require their own evidence. The external tester patch is an archive of its accepted delta, rather than a product-source overlay.
