# CSV support in the existing Telegram test driver

The ordinary DSH file scenario previously admitted TXT inputs and ZIP outputs. The next selected-file task needs a CSV input and a CSV result. This small driver delta supports that combination through the existing serial `distinct-worker-file-task` and `friday_result` delivery path.

The installed driver accepts a pinned `text/csv` input, an exact CSV result basename and MIME type, and the longer bounded task caption. Existing TXT/ZIP and A0 text-result behavior remain supported. The original owner, file identity/hash, closed predecessor, current authority, finite observation window and unknown-send protections remain in place.

The patch is installed in the local test driver. Twenty-seven focused offline checks passed, including actual retained input/predecessor validation, rejection of invalid file bindings, and exact document correlation. The installed Telegram SDK derives `text/csv` from the CSV filename; a fresh driver process also started successfully.

No new Telegram send, model request or worker execution was performed for this patch. The selected-file user task and its contextual continuation remain unaccepted pending the separate DSH admission repair. Previous worker results and uncertain sends were preserved. This is a test-driver checkpoint, not product readiness or full release acceptance.

The patch contains the code delta only. Private inputs, expected answers, credentials, runtime manifests and raw observations are retained outside this publication.
