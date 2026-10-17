Source89 and Source90 public source checkpoint, 2026-10-17.

Source89 adds a sticky web-failure fence with owned-call cleanup and source-aware
PM refresh. Source90 adds checked memory snapshot/proof behavior and receipts
joining the three skill handlers to scope, session, arguments and result. Its
model_tools.py is the accepted ABA-resistant producer (SHA256 5bbc6e4c271182a39150dcc8f000d1d6d515f9dec04381ce1078f300e3f19a0d).

Both accepted patch files remain byte-identical. Only the new manifests' source
prefix/prerequisite hashes are rebound to the public chain. All 45 privacy-repaired
Source87 files and all six published Source88 files remain byte-identical. One
normal scripts/hermes_prepare.py execution produced 90 layers and 17710 physical
files exactly matching the accepted final hashes, sizes and modes. Four dependency
declarations and all eleven protected-compressor assets remain unchanged.

38 source/preparer tests, 23 portable actual-native controls and 21 PM fixture
cases passed. Native controls use real guards, SQLite, dispatcher, registry and
three skill handlers, with synthetic principal/policy records and finite local
provider children. PM controls use real source copying, locks and Facts selection;
the dependency engine is stubbed. These are separate scopes, with no live or
summed-suite claim. The portable native subset does not run the CJK extension case.
The earlier source review retained two reasoned BLE001 allows, listed in STATUS;
its health measurement is not claimed rerun here.

Installed Source90, live model/network/Telegram behavior and final product
acceptance are NOT_RUN / NOT_ESTABLISHED. The new PM API is source-only until a
separately accepted installation; it is not reported as present in installed
Source87. Exact private updater, transaction, runtime bindings, private receipts,
account/session identities and helper packages are withheld. These source checks
are not approval for an installation or a replacement deployment workflow.

Reproduction:
1. Use the Hermes donor commit and tree from sources.lock.json, with its canonical
   origin and a clean index and worktree. No dependency install or model call is
   part of source preparation. Create a fresh private destination parent:

   FRIDAY_SOURCE_AREA=$(mktemp -d)
   chmod 700 "$FRIDAY_SOURCE_AREA"
   python3 -B scripts/hermes_prepare.py --repository "$PWD" \
     --donor "$FRIDAY_DONOR" --destination "$FRIDAY_SOURCE_AREA/native" --seconds 120

   FRIDAY_DONOR is the absolute path of that already pinned donor. The command
   writes native.source.json beside native/. Compare its layers/count and files
   fingerprint with STATUS.json. The fingerprint is SHA256 over:
   (json.dumps(receipt['files'], sort_keys=True, separators=(',', ':'))+'\n').encode()

2. Run the standard-library source identity/preparer suites:

   python3 -B -m unittest discover -s tests -p test_hermes_prepare.py
   python3 -B -m unittest discover -s tests -p test_ordinary_exact_response_source.py
   python3 -B -m unittest discover -s tests -p test_ordinary_source89_90_identity.py

3. Use an existing interpreter with the pinned native dependencies to run the
   portable controls. No installation or dependency resolution is performed by
   these fixtures. Set FRIDAY_TEST_PYTHON to that interpreter's absolute path.
   Linux bubblewrap provides the execution boundary used by this checkpoint:

   FRIDAY_TEST_AREA=$(mktemp -d)
   chmod 700 "$FRIDAY_TEST_AREA"
   mkdir "$FRIDAY_TEST_AREA/home" "$FRIDAY_TEST_AREA/tmp"
   bwrap --unshare-net --ro-bind / / --bind "$FRIDAY_TEST_AREA" "$FRIDAY_TEST_AREA" \
     --dev /dev --proc /proc --chdir "$FRIDAY_TEST_AREA" -- env -i \
     PATH=/usr/bin:/bin LANG=C.UTF-8 HOME="$FRIDAY_TEST_AREA/home" \
     HERMES_HOME="$FRIDAY_TEST_AREA/home" TMPDIR="$FRIDAY_TEST_AREA/tmp" \
     XDG_CONFIG_HOME="$FRIDAY_TEST_AREA/home" XDG_CACHE_HOME="$FRIDAY_TEST_AREA/home" \
     HERMES_TEST_ISOLATION=1 PYTHONDONTWRITEBYTECODE=1 UV_OFFLINE=1 HF_HUB_OFFLINE=1 \
     FRIDAY_NATIVE_SOURCE="$FRIDAY_SOURCE_AREA/native" \
     "$FRIDAY_TEST_PYTHON" -I -B "$PWD/validation/ordinary_source90_native.py"

   Run validation/ordinary_source89_pm.py with the same boundary and interpreter,
   supplying "$FRIDAY_SOURCE_AREA/native" as its single argument. This invokes
   PM only on disposable synthetic source/install fixtures. It does not refresh
   the operator's installation. Both scripts print observations and loaded source
   pins; fixture temporaries and provider children are cleaned up. Retain the
   printed evidence, then remove only the two exact disposable directories.
