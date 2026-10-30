# Ordinary tool argument feedback - source checkpoint

This reviewed patch carries fixed, typed feedback for malformed tool-call JSON
and structured DOCX content through the existing parser, sequential/concurrent
executor, model dispatcher and tool registry. It keeps the existing denial-first
authority checks and discloses no supplied text, paths or nested policy details.
Malformed JSON is never repaired or dispatched. Unsupported formats and generic
scope denials keep their prior behavior. Existing effect accounting is unchanged.

`core.patch` changes eight existing Hermes files from installed Source103. The
same exact patch has an independently checked composition with the accepted
Source104 archive/name leaves; two files overlap. The private combined Source105
preparation is one direct successor from Source103 and needs no Source104 install.
This public bundle contains source and synthetic tests, not installation inputs.

The implementation's 103 checks on Source103 and 103 checks on the Source104
composition passed; independent review added 17 negative controls. Counts have
overlapping scope and are not added together. Packaging reuses these unchanged
results. Tests use synthetic principals, fixed sentinels and temporary homes;
they do not invoke a provider, worker or Telegram. Original failures and UNKNOWN
effects remain recorded without replay. No installed/runtime/user result is
claimed. Installation, fresh native process and real user acceptance remain
separate work.
