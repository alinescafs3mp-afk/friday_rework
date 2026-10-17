Source88 public source chain

Baseline: main 18e60c15c8284e44f2849cb621402c77eaca0109.

The public Source87 prefix already removes a private session identity from an
intermediate layer. The accepted deployment prefix removed that identity at a
later layer instead. Replacing the public prefix with the deployment prefix
would restore private data without changing the final native source.

This publication preserves all existing public prefix bytes, adds the exact
reviewed ordinary-exact-response.patch, and binds its manifest to the public
prefix. The manifest has a new source identity; it is not the private deployment
manifest or an installed-source receipt. The private deployment updater is not
published or enabled by these files.

Normal scripts/hermes_prepare.py composition of both public prefixes was run.
The 87-to-88 transition changes only agent/onboarding.py and
hermes_cli/friday_prompt_scope.py. All 17,708 final source file hashes, sizes and
executable modes match the accepted Source88 source inventory. Eleven protected
assets and pyproject.toml, uv.lock, package.json and package-lock.json are
unchanged. The same 17,590 pinned donor files underlie both compositions.

Reproduce the finite source checks from the repository root:

  python3 -m unittest discover -s tests -p test_hermes_prepare.py -v
  python3 -m unittest discover -s tests -p test_ordinary_exact_response_source.py -v

Compose using the existing pinned donor checkout and a fresh destination whose
parent is a private directory (mode 0700):

  python3 scripts/hermes_prepare.py --repository "$PWD" \
    --donor "$DONOR_CHECKOUT" --destination "$PRIVATE_DESTINATION" --seconds 300
  python3 validation/ordinary_exact_response_prompt.py "$PRIVATE_DESTINATION"

The source identity test binds the immutable Source87 predecessor and Source88
two-body contract; later additive layers are outside that certificate. The
standalone prompt fixture runs normal native restore/build functions with
explicit in-memory admission/storage/tool seams. It verifies stale v6 rebuild,
v7 persistence and reuse, and denial before persistence. It does not demonstrate
model obedience, real admission, real message delivery or installation.

Observed checks: 19 existing source preparation controls, 9 publication identity
controls including wrong prefix/patch/beforeimage/mode refusal, and 9 standalone
native prompt observations. The sets have distinct scopes and are not a live
acceptance count. No native package build or runtime activation was performed
for publication. Existing accepted source/body evidence remains applicable only
where exact source bytes were proved equal.

Source87 remains the reported installed generation. Source88 is source-only;
native source-aware refresh and final runtime acceptance remain separate work.
The exact private v43 updater embeds deployment ancestry and an account-specific
retained filename, so it remains withheld. Its generalization is outside this
publication slice. No runtime-authority hashes, request/input files, captures,
credentials, local handoffs or owner account identifiers are included.
