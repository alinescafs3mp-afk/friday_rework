import copy
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

path = Path(__file__).resolve().parents[1] / "tools/configure_local_test.py"
spec = importlib.util.spec_from_file_location("profile_builder", path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class LocalTestProfile(unittest.TestCase):
    def setUp(self):
        self.args = dict(base_url="http://192.168.50.10:8001/v1", model="dispatcher",
                         key_env="FRIDAY_REWORK_API_KEY", context=40960, max_input=40954,
                         main_output=4096, summary_output=2048, margin=1024, template_overhead=2048)

    def test_exact_route_and_every_enabled_auxiliary_are_pinned(self):
        config = module.build_config(**self.args)
        self.assertEqual(config["model"]["context_length"], 40960)
        self.assertEqual(config["fallback_providers"], [])
        self.assertEqual(config["fallback_model"], {})
        for value in config["auxiliary"].values():
            if isinstance(value, dict):
                self.assertEqual(value["provider"], config["model"]["provider"])
                self.assertEqual(value["base_url"], self.args["base_url"])
                self.assertEqual(value["model"], self.args["model"])
                self.assertEqual(value["fallback_chain"], [])
        self.assertEqual(config["auxiliary"]["compression"]["extra_body"], {"max_tokens": 2048})

    def test_larger_profile_does_not_inherit_temporary_capacity(self):
        args = dict(self.args, model="future-fixture", context=131072, max_input=130000)
        config = module.build_config(**args)
        row = config["providers"]["friday-local"]["models"]["future-fixture"]
        self.assertEqual(row["context_length"], 131072)
        self.assertEqual(row["bounded_context"]["server_max_input_tokens"], 130000)
        self.assertGreater(config["compression"]["threshold_tokens"], 40960)

    def test_public_or_ambiguous_routes_reject(self):
        for url in ("https://api.openai.com/v1", "http://8.8.8.8:8001/v1",
                    "http://user:secret@127.0.0.1:8001/v1", "http://127.0.0.1:8001/v1?key=x",
                    "http://@127.0.0.1:8001/v1", "http://127.0.0.1:8001/v1\n"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                module.build_config(**dict(self.args, base_url=url))

    def test_model_id_cannot_change_during_native_environment_loading(self):
        for model in ("${FIXTURE_MODEL}", "Auto", "auto", "dispatcher\n", "dis\x00patcher"):
            with self.subTest(model=model), self.assertRaises(ValueError):
                module.build_config(**dict(self.args, model=model))

    def test_backup_must_retain_independent_original_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            original = Path(temp) / "config.yaml"
            original.write_bytes(b"original fixture")
            original.chmod(0o600)
            backup = Path(temp) / "backup.yaml"
            backup.symlink_to(original)
            with self.assertRaises(OSError):
                module.read_owned_file(backup, private=True)
            backup.unlink()
            os.link(original, backup)
            with self.assertRaises(ValueError):
                module.read_owned_file(backup, private=True)
            backup.unlink()
            backup.write_bytes(original.read_bytes())
            backup.chmod(0o600)
            original.write_bytes(b"replacement fixture")
            self.assertEqual(module.read_owned_file(backup, private=True), b"original fixture")
            backup.chmod(0o644)
            with self.assertRaises(ValueError):
                module.read_owned_file(backup, private=True)

    def test_invalid_or_impossible_capacity_rejects(self):
        for delta in ({"context": True}, {"margin": 0}, {"max_input": 50000},
                      {"main_output": 40960}, {"summary_output": -1}):
            with self.subTest(delta=delta), self.assertRaises(ValueError):
                module.build_config(**dict(self.args, **delta))

    def test_independent_profile_values_do_not_mutate_each_other(self):
        first = module.build_config(**self.args)
        before = copy.deepcopy(first)
        module.build_config(**dict(self.args, model="second-fixture"))
        self.assertEqual(first, before)


if __name__ == "__main__":
    unittest.main()
