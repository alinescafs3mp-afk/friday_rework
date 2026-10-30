# CORE ZIP, PDF OCR and inbound filename delta — Source102

[core.patch](core.patch) applies at the Hermes source root after the [Source101 relative MEDIA and JSON masking delta](../core-relative-media-json-mask-20261030/README.md). It contains exactly nine product files, including two new helpers. [MANIFEST.json](MANIFEST.json) gives their exact before/after hashes. The existing [Hermes license](../../LICENSE-Hermes.txt) and [attribution](../../THIRD_PARTY_NOTICES.md) apply. This is source material for review; it is not an installer or a complete distribution.

Source102 was installed once on the existing native98 dependency generation, and its source integrity was accepted by a fresh process. The ordinary gateway and Dashboard were verified under permanent management. New ZIP, scanned-PDF OCR and inbound filename user paths have not received semantic acceptance. DSH remains unavailable because its policy expired; A0 is deferred. [STATUS.json](STATUS.json) keeps these facts separate.

| Product file | Change |
| --- | --- |
| `gateway/run_inbound.py` | Uses the verified inbound attachment's presentation name in document context. |
| `gateway/run_inbound_media.py` | Retains original-name metadata through the verified copy and exposes a presentation-only name. |
| `hermes_cli/friday_prompt_scope.py` | Describes bounded ZIP listing, creation and extraction, including continuation and explicit unsupported 7z handling. |
| `hermes_cli/friday_user_scope.py` | Routes ZIP operations and carries trusted PDF extraction coverage through read pagination. |
| `hermes_cli/friday_workspace_zip.py` | Adds explicit-member ZIP creation, paginated inspection and extraction to a new directory with custody checks. |
| `plugins/platforms/telegram/telegram_file_boundary.py` | Records the original inbound filename as presentation metadata. |
| `tools/file_tools.py` | Exposes the ZIP formats to the existing file-tool schema. |
| `tools/read_extract.py` | Routes PDF extraction through the bounded local helper. |
| `tools/scoped_pdf_ocr.py` | Adds finite local PDF text/OCR extraction with structured coverage metadata and process cleanup. |

ZIP scope is limited to 128 entries and 1 MB of uncompressed data, uses exact listed files, and refuses existing destinations, unsafe paths, links, encrypted entries and unsupported compression. The OCR helper uses a fixed local toolchain and private networkless execution; that toolchain is not bundled here. The filename change affects inbound presentation only. Outbound original-name preservation, 7z support and the later memory-write mitigation are outside this patch.

[MEMORY-RESULTS.json](MEMORY-RESULTS.json) records earlier Source101 observations. M-04 has independent scoped acceptance for selecting the correct same-name original and delivering its exact bytes; inbound and outbound filename presentation failed in that observation. M-05 correctly recalled the central workbook edit and arithmetic, but invented worksheet and named-range details, so its full semantic result is FAIL. Its genuine elapsed lower bound is 8,775 seconds, established from the original delivery and the recall run; the separate fixture-age axis was not run. M-06 remains FAIL: the ODT preference was not written despite the acknowledgement; the later DOCX write started from an already-DOCX state, and recall falsely described an ODT-to-DOCX transition. M-07 was refused before a new send because the request already existed. None of these observations establishes full memory or product readiness.

Publication verified exact reverse/forward patch application, all nine byte hashes, Python syntax and public-data boundaries. The independent memory review inspected retained files and closed observations. No product test, model request, document generation, user-message replay or service action was performed for this checkpoint. Private integration machinery, runtime paths, identifiers, raw user content and expected-answer data are excluded.
