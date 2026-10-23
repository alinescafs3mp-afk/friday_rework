# Source117: genuine gateway and fresh DOCX result

Source117/project309 is installed. Its supported native gateway startup returned 0 in 81.245 seconds. The permanent gateway remains running under Root ownership; workers are off.

One genuinely new DOCX request used a fresh nonce and filename. It was sent once, with the full 180-second receive window and original native300/user600 budgets. Delivery and native custody passed all 23 checks. Independent semantics failed: **25 passed, 7 failed, 5 not evaluated out of 37**. The received file contains literal Markdown headings and tab-separated paragraphs, with no actual Word headings or table. The previous R116 failure remains unchanged; no request was replayed.

All four accepted structured-DOCX repair files are present in the installed version. The model selected the existing plain `docx` mode instead of `docx_structured`. An initial explanation that the repair was missing was corrected against actual installed hashes; no duplicate patch or reinstallation followed. Whether the full current deferred-tool schema reached this request is not established, and the source-side exposure/selection path remains under investigation.

[OBSERVATIONS.json](OBSERVATIONS.json) records separate installation, startup, delivery and semantic facts. [SHA256SUMS](SHA256SUMS) authenticates these public files. This result does not establish product readiness or full release acceptance.
