# UNBOUND ANALYSIS EXCERPT. Incomplete dependencies; not a runnable tester.
# Original operational values are omitted; see SOURCE-PROVENANCE.json.
# Noncontiguous statement excerpts; surrounding control flow is intentionally absent.
class TesterExcerpt:
    def _send_selected_statements(self, run):
        remaining = self.guard(run, http_cap=30)
        preflight(self.api, remaining, lambda: self.guard(run, http_cap=30))
