The recursive-request negative test assumed that a JSON array nested 20,000 levels would always make the decoder raise `RecursionError`. The selected CPython 3.14.4 C decoder accepts those bytes. The application then correctly refuses the non-object request without changing current files.

The corrected test checks that ordinary refusal, then injects a decoder `RecursionError` in a scoped patch to verify the exact redacted failure, one decoder call, no writes and decoder restoration. The existing parameter IDs and suite membership are unchanged. Product and native implementation bytes are unchanged.

The actual migration group completed: 83 passed, 267 deselected, in 17.07 seconds. The overall 350-case run remains failed: the separate 142-case archive group reached its unchanged 100-second limit before completing. Its unfinished cases and missing final evidence remain unaccepted. Diagnosis needs phase timing; no product hang or fixture defect has been established from the existing partial log.

This records a test correction and its completed group validation. It does not establish a passing full gate, installation, a production capacity change, runtime acceptance or release readiness.
