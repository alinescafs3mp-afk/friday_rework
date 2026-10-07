import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.web_profile import dsh_web_patch, hermes_web_config, research_policy


def renderer(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HERMES = renderer("configure_local_test")
DSH = renderer("render_dsh_local")
HERMES_INPUT = dict(base_url="http://127.0.0.1:8011/v1", model="local-fixture",
                   key_env="FRIDAY_FIXTURE_KEY", context=40960, max_input=40954,
                   main_output=4096, summary_output=2048, margin=1024, template_overhead=2048)
DSH_INPUT = dict(purpose="temporary-local-test", api="openai-completions",
                base_url="http://127.0.0.1:8011/v1", model="local-fixture",
                context_window=40960, max_tokens=4096, summary_max_tokens=2048,
                headroom_tokens=4096)


class WebProfiles(unittest.TestCase):
    def test_disabled_means_original_component_config(self):
        self.assertEqual(hermes_web_config(), {})
        self.assertEqual(dsh_web_patch(), [])
        config = HERMES.build_config(**HERMES_INPUT)
        self.assertEqual(config["toolsets"], [])
        self.assertNotIn("web", config)
        self.assertNotIn("environment_hint", config["agent"])
        self.assertTrue(next(r for r in DSH.build_patch(**DSH_INPUT)
                             if r["id"] == "tool-web")["disabled"])

    def test_hermes_web_changes_only_retrieval_and_additive_policy(self):
        before = HERMES.build_config(**HERMES_INPUT)
        for profile in ("exa-paid", "exa-keyless"):
            config = HERMES.build_config(**HERMES_INPUT, web_profile=profile)
            self.assertEqual(config["toolsets"], ["web"])
            self.assertEqual(config["agent"].pop("environment_hint"), research_policy())
            self.assertEqual(config["platform_toolsets"], {"cli": ["web"], "telegram": ["web"]})
            for key in ("web", "plugins", "platform_toolsets"):
                del config[key]
            config["toolsets"] = []
            self.assertEqual(config, before)
            self.assertNotIn("system_prompt", config["agent"])
            self.assertNotIn("display", config)

    def test_hermes_profiles_have_one_explicit_provider_and_no_rescue(self):
        for profile, keyless in (("exa-paid", False), ("exa-keyless", True)):
            web = hermes_web_config(profile)["web"]
            self.assertEqual([web[k] for k in ("backend", "search_backend", "extract_backend")],
                             ["exa"] * 3)
            self.assertIs(web["keyless_fallback"], keyless)
            self.assertIs(web["keyless_rescue"], False)
            ring = [k for k, v in web["provider_tier"].items() if v != "paid"]
            self.assertEqual(ring, ["exa"] if keyless else [])
            self.assertFalse(web["cache_enabled"])
        web = hermes_web_config("exa-keyless", extract_char_limit=3000, extract_timeout=7)["web"]
        self.assertEqual((web["extract_char_limit"], web["extract_timeout"]), (3000, 7))

    def test_dsh_inserts_exa_and_replaces_cloud_search_selection(self):
        patch_rows = DSH.build_patch(**DSH_INPUT, web_profile="exa-paid")
        baseline = DSH.build_patch(**DSH_INPUT)
        rows = {r["id"]: r for r in patch_rows if "id" in r}
        self.assertEqual(len(rows) + 1, len(patch_rows))
        self.assertEqual(patch_rows[:3], baseline[:3])
        self.assertEqual(rows["web"]["config"], {"searchProvider": "exa", "fetchProvider": "http"})
        insert = next(r["insert"] for r in patch_rows if "insert" in r)
        self.assertEqual(insert[0]["id"], "web-search-exa")
        self.assertEqual(insert[0]["name"], "@deepseek-ai/dsh-web-search-exa")
        self.assertNotIn("apiKey", insert[0]["config"])
        self.assertNotIn("apiKeyEnv", insert[0]["config"])  # Native Exa reads EXA_API_KEY.
        self.assertFalse(rows["tool-web"]["disabled"])
        self.assertFalse(rows["web-fetch-http"]["disabled"])
        for row in DSH.DISABLED_ROWS:
            if row != "tool-web":
                self.assertTrue(rows[row]["disabled"])
        self.assertNotIn("system-prompt", rows)

    def test_native_dsh_budgets_are_separate_from_model_budgets(self):
        result = DSH.build_patch(**DSH_INPUT, web_profile="exa-paid", web_search_max_results=3,
                                web_search_max_queries=1, web_timeout_ms=7000,
                                web_fetch_max_chars=8000, web_fetch_max_bytes=64000)
        rows = {r["id"]: r for r in result if "id" in r}
        tool = rows["tool-web"]["config"]
        self.assertEqual((tool["searchMaxResults"], tool["searchMaxQueries"]), (3, 1))
        self.assertEqual((tool["searchTimeoutMs"], tool["fetchTimeoutMs"]), (7000, 7000))
        self.assertEqual(rows["web-fetch-http"]["config"]["maxResponseBytes"], 64000)
        self.assertEqual(result[:3], DSH.build_patch(**DSH_INPUT)[:3])

    def test_unsupported_and_injected_profiles_are_rejected(self):
        for value in (None, True, {}, [], "", "auto", "nous", "xai", "openai-native",
                      "deepseek-official", "exa-paid\n", "${EXA_API_KEY}",
                      "!!js process.env.EXA_API_KEY", "https://user:canary@host/"):
            for build in (hermes_web_config, dsh_web_patch):
                with self.subTest(value=value, build=build.__name__), self.assertRaises(ValueError):
                    build(value)
        with self.assertRaises(ValueError):
            dsh_web_patch("exa-keyless")  # This donor has no native keyless Exa provider.

    def test_invalid_limits_do_not_silently_enable_or_relax_tools(self):
        specifications = (
            (hermes_web_config, "extract_char_limit", 2000, 500000),
            (hermes_web_config, "extract_timeout", 1, 120),
            (dsh_web_patch, "search_max_results", 1, 20),
            (dsh_web_patch, "search_max_queries", 1, 4),
            (dsh_web_patch, "timeout_ms", 1, 120000),
            (dsh_web_patch, "fetch_max_chars", 2000, 200000),
            (dsh_web_patch, "fetch_max_bytes", 1, 5000000),
        )
        for build, key, low, high in specifications:
            for valid in (low, high):
                build("exa-paid", **{key: valid})
            for bad in (True, False, "30", 1.5, 0, -1, low - 1, high + 1, float("inf")):
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    build("exa-paid", **{key: bad})
            with self.assertRaises(ValueError):
                build("disabled", **{key: low})

    def test_fresh_profiles_ignore_environment_and_share_no_mutable_values(self):
        for build in (hermes_web_config, dsh_web_patch):
            first = build("exa-paid")
            snapshot = copy.deepcopy(first)
            with patch.dict(os.environ, {"EXA_API_KEY": "SECRET_CANARY",
                                        "DEEPSEEK_API_KEY": "SECRET_CANARY",
                                        "DSH_WEB_SEARCH_PROVIDER": "deepseek-official",
                                        "HERMES_ENVIRONMENT_HINT": "HOSTILE_POLICY"}):
                second = build("exa-paid")
            self.assertEqual(first, second)
            self.assertNotIn("SECRET_CANARY", json.dumps(second))
            self.assertNotIn("HOSTILE_POLICY", json.dumps(second))
            if isinstance(second, dict):
                second["web"]["backend"] = "changed"
            else:
                second[0]["config"]["searchProvider"] = "changed"
            self.assertEqual(first, snapshot)

    def test_cli_invalid_web_input_redacts_values_and_has_no_effect(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "patch.json"
            dsh_args = [sys.executable, "-B", str(ROOT / "tools/render_dsh_local.py")]
            for key, value in DSH_INPUT.items():
                dsh_args += ["--" + key.replace("_", "-"), str(value)]
            dsh_args += ["--output", str(output)]
            hermes_args = [sys.executable, "-B", str(ROOT / "tools/configure_local_test.py"),
                           "--home", str(ROOT / ".runtime/uncreated-web-negative")]
            for key, value in HERMES_INPUT.items():
                hermes_args += ["--" + key.replace("_", "-"), str(value)]
            for argv in (dsh_args, hermes_args):
                for suffix in (["--web-profile", "SECRET_CANARY"],
                               ["--web-profile", "exa-paid", "--web-profile", "SECRET_CANARY"],
                               ["--web-profile", ""], ["--web-unknown", "SECRET_CANARY"]):
                    result = subprocess.run(argv + suffix, capture_output=True, timeout=10)
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertNotIn(b"SECRET_CANARY", result.stdout + result.stderr)
            self.assertFalse(output.exists())
            self.assertFalse((ROOT / ".runtime/uncreated-web-negative").exists())

    def test_dsh_enabled_cli_publishes_reference_only_profile(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "patch.json"
            argv = [sys.executable, "-B", str(ROOT / "tools/render_dsh_local.py")]
            for key, value in DSH_INPUT.items():
                argv += ["--" + key.replace("_", "-"), str(value)]
            argv += ["--web-profile", "exa-paid", "--output", str(output)]
            with patch.dict(os.environ, {"EXA_API_KEY": "SECRET_CANARY"}):
                result = subprocess.run(argv, capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(output.read_bytes()), DSH.build_patch(**DSH_INPUT, web_profile="exa-paid"))
            self.assertNotIn(b"SECRET_CANARY", output.read_bytes() + result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
