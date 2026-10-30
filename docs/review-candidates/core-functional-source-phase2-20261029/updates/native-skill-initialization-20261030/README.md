Native skill initialization: source-only delta

The first native skill creation can fail with an active UserScope because the configuration loader creates an empty skills directory after the registry has captured its absent-directory CAS precondition. The four-line change leaves that directory's publication to the native registry while retaining initialization of the other ordinary directories.

The retained implementation was independently checked against the original configuration loader: exact skill bytes are persisted, the original defect is reproduced as a negative control, and a separate process lists and reads the same saved skill and exposes its name in the native prompt index. These focused checks use an isolated capability fixture; actual PairingStore/database ACL and Telegram semantic reuse are not established by them. Original failed/incomplete observations remain preserved privately.

Status: reviewed implementation in source artifacts; not installed, ordinary Telegram M10 NOT_RUN. This delta is separate from the in-progress Source105 installation and must be integrated against the actual baseline before a future bounded installation. No model, endpoint, worker contract or runtime setting is changed by this publication.
