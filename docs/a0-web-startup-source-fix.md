# A0 web startup and failure evidence

The web startup command now installs the two existing pinned search overlays
after the image copy step and before supervision. The installer checks both
original files and replacement hashes before writing, checks each original
again before replacement, preserves file modes and verifies the resulting
hashes. A rejected installer stops the shell before supervision, including
when the shell does not enable `errexit`. Startup without web stays unchanged.

The service probe uses standard-library XMLRPC over the existing private Unix
socket. It no longer depends on importing the supervisor package from the
isolated SearXNG environment. Source pins, service settings, process ownership,
version, network checks and existing timeout limits remain in force.

A probe exception produces only an allowlisted phase and exception class.
The host rejects that report and retains it in the existing native receipt;
it does not treat a reported failure as healthy. Receipt merging preserves
observations and checks the same plan, container and invocation identity.
Exception messages, secrets and tracebacks are not exported by this diagnostic.

Run the focused offline checks with:

```sh
python3 -B -m unittest discover -s tests -p test_a0_web_startup.py -v
```

The 13 checks cover overlay payload hashes, neutral installer preimages,
mode preservation, drift/symlink/repeat refusals, shell short-circuiting,
bounded diagnostics, receipt ownership and a real temporary Unix XMLRPC
exchange. The existing web admission test also follows the generated startup
command and supplies the endpoint set declared by the runtime under test.

These are source and isolated transport checks. They do not establish that
the repaired image was installed, that a container passed qualification or
that a user task succeeded. The unavailable original web-check stderr does
not establish which defect caused the first historical exception. Updated
source hashes and a fresh process are required at the separately authorized
installation and qualification boundary.
