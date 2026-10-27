# Worker state quota and admission diagnostics

The Friday worker association store exceeded the default 10 MiB plugin quota while retaining earlier jobs and accepting an input-bearing assignment. This change gives the exact `friday_rework` plugin a 64 MiB quota; other plugins retain 10 MiB. The portable native patch applies after the public private-state overlay. The canonical metadata reader already consumes `state.quota_bytes`. No history or user data is deleted.

Admission and setup failures now retain protected, bounded diagnostics: phase, exception class, allowlisted source frames and hashed request correlation. Public refusal behavior is unchanged. Exception messages, arguments, credentials and user content are excluded.

Validation: five diagnostic controls, two quota tests against the composed native source, and nineteen source-preparer tests passed. The installed private quota/diagnostic combination was separately checked by a fresh consumer before the subsequent host reboot. The portable patch is a source publication, not a new installation or completed user milestone.

At this checkpoint, the new Telegram DSH assignment was interrupted by the host reboot before native submission; its reservation was reconciled without replay. Gateway and Dashboard were restored. Worker use still requires the current-boot policy/qualification repair. A0 web/stop composition remains separate work.
