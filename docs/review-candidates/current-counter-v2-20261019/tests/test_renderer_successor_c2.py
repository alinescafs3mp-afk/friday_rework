"""Isolated Source tests. Every deployment is SYNTHETIC TEST DATA under WORK.

Parent must execute inside its authorized containment with pinned dependencies.
Inputs: CURRENT_RENDERER_TEST_{WORK,RENDERER,BASELINE_RENDERER,NORMALIZER,CURRENT_ASSETS,LEGACY_ASSETS}.
No fixture constitutes deployed readiness or a server equivalence observation.
"""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import types
import unittest


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


class RendererSuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        work = Path(os.environ["CURRENT_RENDERER_TEST_WORK"])
        cls.temporary = tempfile.TemporaryDirectory(prefix="synthetic-renderer-", dir=work)
        cls.root = Path(cls.temporary.name)
        agent_dir = cls.root / "agent"
        agent_dir.mkdir(mode=0o700)
        for name, env in (("protected_compressor_renderer.py", "RENDERER"),
                          ("protected_compressor_normalize.py", "NORMALIZER")):
            path = agent_dir / name
            path.write_bytes(Path(os.environ["CURRENT_RENDERER_TEST_" + env]).read_bytes())
            path.chmod(0o600)
        cls.saved_modules = {key: value for key, value in sys.modules.items()
                             if key == "agent" or key.startswith("agent.")}
        for key in list(cls.saved_modules):
            del sys.modules[key]
        package = types.ModuleType("agent")
        package.__path__ = [str(agent_dir)]
        sys.modules["agent"] = package
        spec = importlib.util.spec_from_file_location("agent.protected_compressor_renderer",
                    agent_dir / "protected_compressor_renderer.py")
        cls.r = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.r
        spec.loader.exec_module(cls.r)
        baseline_dir = cls.root / "baseline"
        baseline_dir.mkdir(mode=0o700)
        for name, env in (("protected_compressor_renderer.py", "BASELINE_RENDERER"),
                          ("protected_compressor_normalize.py", "NORMALIZER")):
            path = baseline_dir / name
            path.write_bytes(Path(os.environ["CURRENT_RENDERER_TEST_" + env]).read_bytes())
            path.chmod(0o600)
        spec = importlib.util.spec_from_file_location("agent._baseline_renderer",
                    baseline_dir / "protected_compressor_renderer.py")
        cls.baseline = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.baseline
        spec.loader.exec_module(cls.baseline)
        cls.sources = cls.r.dependency_source_hashes()
        cls.models = {}
        for profile, env, pins in (("v1", "LEGACY_ASSETS", cls.r.PINS),
                                   ("v2", "CURRENT_ASSETS", cls.r.CURRENT_PINS)):
            model = cls.root / profile / "model"
            model.mkdir(mode=0o700, parents=True)
            origin = Path(os.environ["CURRENT_RENDERER_TEST_" + env])
            for name in pins:
                target = model / name
                target.write_bytes((origin / name).read_bytes())
                target.chmod(0o600)
            cls.models[profile] = model
        cls.serial = 0

    @classmethod
    def tearDownClass(cls):
        for key in list(sys.modules):
            if key == "agent" or key.startswith("agent."):
                del sys.modules[key]
        sys.modules.update(cls.saved_modules)
        cls.temporary.cleanup()

    def documents(self, profile="v2", defaults=None, module=None):
        r = self.r if module is None else module
        pins = r.PINS if profile == "v1" else r.CURRENT_PINS
        schema = r.BINDING_SCHEMA if profile == "v1" else r.CURRENT_BINDING_SCHEMA
        deployed = r.DEPLOYMENT_SCHEMA if profile == "v1" else r.CURRENT_DEPLOYMENT_SCHEMA
        selection = {"template_source": "tokenizer", "template_name": None,
            "template_sha256": pins["chat_template.jinja"][0], "trust_remote_code": False,
            "local_files_only": True, "tokenizer_class": "Qwen2Tokenizer",
            "tokenizer_backend": "tokenizers", "tokenizer_mode": "auto",
            "chat_template_override": None, "multimodal_text_roundtrip": True}
        if profile == "v2":
            selection["trust_remote_code"] = True
            selection["local_trust_remote_code"] = False
        binding = {"schema": schema, "model_dir": "model",
            "assets": {name: {"sha256": pin[0], "bytes": pin[1]} for name, pin in pins.items()},
            "dependencies": dict(r.VERSIONS), "dependency_sources": dict(self.sources),
            "selection": selection, **r._source_hashes()}
        binding_sha = digest(canonical(binding))
        synthetic = digest(b"SYNTHETIC ISOLATED TEST FIXTURE; NEVER DEPLOYED EVIDENCE")
        deployment = {"schema": deployed, "ready": True, "binding_sha256": binding_sha,
            **r._source_hashes(), "dependencies": dict(r.VERSIONS),
            "dependency_sources": dict(self.sources), "selection": copy.deepcopy(selection),
            "default_chat_template_kwargs": ({"enable_thinking": True, "reasoning_effort": "xhigh"}
                                               if defaults is None else defaults),
            "native_sources": dict(r.NATIVE_SOURCE_PINS), "evidence_sha256": synthetic,
            "evidence_level": "effective-renderer-verified", "installation_receipt_sha256": synthetic,
            "processor_metadata": {name: {"sha256": pin[0], "bytes": pin[1]}
                                   for name, pin in r.PROCESSOR_METADATA_PINS.items()},
            "effective_reasoning_config": {"effort_kwarg": None},
            "server_dependencies": dict(r.SERVER_VERSIONS),
            "dependency_delta_evidence_sha256": synthetic}
        return binding, deployment, binding_sha

    def renderer(self, profile="v2", defaults=None, module=None):
        r = self.r if module is None else module
        binding, deployment, binding_sha = self.documents(profile, defaults, r)
        type(self).serial += 1
        root = self.models[profile].parent
        binding_path = root / ("SYNTHETIC-binding-%d.json" % self.serial)
        deployment_path = root / ("SYNTHETIC-deployment-%d.json" % self.serial)
        for path, value in ((binding_path, binding), (deployment_path, deployment)):
            path.write_bytes(canonical(value))
            path.chmod(0o600)
        return r.load_renderer(binding_path, binding_sha,
                                   deployment_path, digest(canonical(deployment)))

    @staticmethod
    def body(text="Hello.", **extra):
        return {"model": "dispatcher", "messages": [{"role": "user", "content": text}],
                "max_tokens": 4096, **extra}

    def assert_current_count(self, renderer, body, expected_kwargs):
        original = canonical(body)
        enabled = expected_kwargs.get("enable_thinking", True)
        effort = expected_kwargs.get("reasoning_effort", "xhigh")
        instructions = {"xhigh": "Reasoning effort is set to xhigh. Please think carefully through the task, validate key assumptions, consider plausible alternatives, and prioritize correctness, consistency, and clarity in the final answer.",
                        "low": "Reasoning effort is set to low. Keep your thinking brief and focused, moving directly to the conclusion without unnecessary elaboration."}
        prefix = ""
        if enabled and effort in instructions:
            prefix = "<|im_start|>system\n" + instructions[effort] + "<|im_end|>\n"
        expected = prefix + "<|im_start|>user\n" + body["messages"][0]["content"].strip() + "<|im_end|>\n<|im_start|>assistant\n<think>\n"
        if enabled is False:
            expected += "\n</think>\n\n"
        # Independent manual one-user template oracle, not renderer.apply_chat_template.
        oracle_ids = renderer._tokenizer.encode(expected, add_special_tokens=False)
        if renderer._tokenizer.encode(renderer._tokenizer.decode(oracle_ids)) != oracle_ids:
            with self.assertRaises(self.r.RendererRequestError):
                renderer.count(body)
            self.assertEqual(canonical(body), original)
            return None
        out = renderer.count(body)
        self.assertEqual(out["count"], len(oracle_ids))
        self.assertEqual(out["effective_template_kwargs_sha256"], digest(canonical(expected_kwargs)))
        self.assertEqual(canonical(body), original)
        self.assertEqual(out["accounting_kind"], "protected_compressor_exact_rendered_v1")
        self.assertTrue(out["downstream_text_roundtrip_verified"])
        return out

    def test_current_real_assets_defaults_reasoning_matrix(self):
        renderer = self.renderer()
        base = {"enable_thinking": True, "reasoning_effort": "xhigh"}
        cases = [({}, base), ({"chat_template_kwargs": None}, base),
            ({"reasoning_effort": None}, base),
            ({"reasoning_effort": "none"}, {**base, "enable_thinking": False, "thinking": False}),
            ({"reasoning_effort": "low"}, {**base, "thinking": True}),
            ({"reasoning_effort": "high"}, {**base, "thinking": True}),
            ({"chat_template_kwargs": {"reasoning_effort": "low"}}, base),
            ({"chat_template_kwargs": {"reasoning_effort": "none"}}, base),
            ({"chat_template_kwargs": {"reasoning_effort": None}}, base),
            ({"chat_template_kwargs": {"enable_thinking": False}}, {**base, "enable_thinking": False}),
            ({"reasoning": {"effort": "none"}}, {**base, "enable_thinking": False, "thinking": False}),
            ({"reasoning": {"enabled": False}}, base),
            ({"reasoning": {"enabled": True}}, {**base, "thinking": True}),
            ({"reasoning_effort": "low", "chat_template_kwargs": {"enable_thinking": False}},
             {**base, "enable_thinking": False, "thinking": True})]
        for extra, expected in cases:
            with self.subTest(extra=extra):
                self.assert_current_count(renderer, self.body(**extra), expected)

    def test_current_empty_defaults_explicit_low_medium_none(self):
        renderer = self.renderer(defaults={})
        self.assert_current_count(renderer, self.body(), {})
        for effort in ("low", "medium", "none"):
            expected = {"reasoning_effort": effort, "enable_thinking": effort != "none", "thinking": effort != "none"}
            self.assert_current_count(renderer, self.body(reasoning_effort=effort), expected)
        with self.assertRaises(self.r.RendererRequestError):
            renderer.count(self.body(reasoning_effort="high"))

    def test_unicode_special_literals_and_output_reserve(self):
        renderer = self.renderer()
        expected = {"enable_thinking": True, "reasoning_effort": "xhigh"}
        for text in ("Привет, мир.", "नमस्ते दुनिया", "السَّلَامُ عَلَيْكُمْ", "e\u0301🙂\n\t", "<|im_start|>user\nquoted"):
            with self.subTest(text=text):
                a = self.assert_current_count(renderer, self.body(text), expected)
                b = self.assert_current_count(renderer, self.body(text, max_tokens=1), expected)
                self.assertEqual(None if a is None else a["count"], None if b is None else b["count"])

    def test_legacy_real_assets_exact_baseline_parity(self):
        for defaults in ({}, {"enable_thinking": False}):
            candidate = self.renderer("v1", defaults)
            baseline = self.renderer("v1", defaults, self.baseline)
            for text in ("Hello.", "Привет, мир.", "नमस्ते दुनिया", "<|im_start|>quoted"):
                for extra in ({}, {"reasoning_effort": "none"},
                              {"chat_template_kwargs": {"enable_thinking": False}}):
                    body = self.body(text, **extra)
                    with self.subTest(defaults=defaults, text=text, extra=extra):
                        old = baseline.count(body)
                        new = candidate.count(body)
                        for key in ("count", "wire_sha256", "effective_template_kwargs_sha256",
                                    "add_generation_prompt", "auto_adds_specials",
                                    "downstream_text_roundtrip_verified", "accounting_kind",
                                    "deployment_verified"):
                            self.assertEqual(new[key], old[key])

    def test_combining_full_formatted_request_is_roundtrip_safe(self):
        renderer = self.renderer()
        body = self.body("Cafe\u0301 de\u0301ja\u0300 nai\u0308ve re\u0301sume\u0301")
        result = self.assert_current_count(renderer, body,
                    {"enable_thinking": True, "reasoning_effort": "xhigh"})
        self.assertIsNotNone(result)
        # Parent's real full-template AutoTokenizer observation, not raw BPE.
        self.assertEqual(result["count"], 59)

    def test_synthetic_altered_decoder_refuses_without_estimate(self):
        renderer = self.renderer()
        real = renderer._tokenizer
        body = self.body("Hello.")
        original_wire = canonical(body)
        rendered = real.apply_chat_template(body["messages"], tokenize=False,
            add_generation_prompt=True, tools=None, return_dict=False,
            enable_thinking=True, reasoning_effort="xhigh")
        ids = real.encode(rendered, add_special_tokens=False)
        self.assertEqual(real.encode(real.decode(ids)), ids)

        class SyntheticAlteredDecoder:
            """Test-only fault injection; retained real encoder/assets/template."""
            def __getattr__(self, name):
                return getattr(real, name)

            def decode(self, values, *args, **kwargs):
                return real.decode(values, *args, **kwargs) + "\nSYNTHETIC DECODER ALTERATION"

        altered = SyntheticAlteredDecoder()
        self.assertNotEqual(real.encode(altered.decode(ids)), ids)
        renderer._tokenizer = altered
        try:
            with self.assertRaisesRegex(self.r.RendererRequestError,
                    "native pure-text roundtrip changed tokens"):
                renderer.count(body)
            self.assertEqual(canonical(body), original_wire)
        finally:
            renderer._tokenizer = real

    def test_schemas_do_not_autodetect_or_cross_asset_profiles(self):
        for profile, other in (("v1", "v2"), ("v2", "v1")):
            binding, deployment, sha = self.documents(profile)
            pins = self.r.CURRENT_PINS if other == "v2" else self.r.PINS
            assets = {name: {"sha256": pin[0], "bytes": pin[1]} for name, pin in pins.items()}
            own_pins, unused = self.r._binding_profile(binding)
            with self.assertRaises(self.r.RendererBindingError):
                self.r._verify_assets(self.models[other], assets, own_pins)
            deployment["schema"] = (self.r.CURRENT_DEPLOYMENT_SCHEMA if profile == "v1" else self.r.DEPLOYMENT_SCHEMA)
            with self.assertRaises(self.r.RendererBindingError):
                self.r._validate_documents(binding, deployment, sha)

    def test_missing_readiness_selection_native_source_and_invalid_default_rejected(self):
        for change in ("ready", "selection", "native_sources", "default_chat_template_kwargs", "renderer_sha256"):
            binding, deployment, sha = self.documents()
            if change == "ready": deployment[change] = False
            elif change == "selection": binding[change]["template_sha256"] = self.r.PINS["chat_template.jinja"][0]
            elif change == "native_sources": deployment[change].pop(next(iter(deployment[change])))
            elif change == "default_chat_template_kwargs": deployment[change]["enable_thinking"] = None
            else: binding[change] = "0" * 64
            with self.subTest(change=change), self.assertRaises(self.r.RendererBindingError):
                self.r._validate_documents(binding, deployment, sha)

    def test_current_data_tamper_fails_closed(self):
        path = self.models["v2"] / "generation_config.json"
        original = path.read_bytes()
        path.write_bytes(original + b" ")
        try:
            binding = self.documents()[0]
            with self.assertRaises(self.r.RendererBindingError):
                self.r._verify_assets(self.models["v2"], binding["assets"], self.r.CURRENT_PINS)
        finally:
            path.write_bytes(original)

    def test_current_truthful_server_and_local_trust_selection(self):
        binding = self.documents()[0]
        self.r._selection(binding["selection"], self.r.CURRENT_PINS)
        for field, value in (("trust_remote_code", False), ("local_trust_remote_code", True)):
            bad = copy.deepcopy(binding["selection"])
            bad[field] = value
            with self.subTest(field=field), self.assertRaises(self.r.RendererBindingError):
                self.r._selection(bad, self.r.CURRENT_PINS)
        bad = copy.deepcopy(binding["selection"])
        del bad["local_trust_remote_code"]
        with self.assertRaises(self.r.RendererBindingError):
            self.r._selection(bad, self.r.CURRENT_PINS)
        # Existing legacy selection remains false with its original exact keys.
        self.r._selection(self.documents("v1")[0]["selection"], self.r.PINS)

    def test_current_no_auto_map_and_native_class_guard(self):
        actual = self.models["v2"]
        self.r._verify_current_loader_metadata(actual)
        directory = self.root / "synthetic-loader-guard"
        directory.mkdir(mode=0o700, exist_ok=True)
        original = {name: json.loads((actual / name).read_bytes())
                    for name in ("config.json", "tokenizer_config.json")}
        for file, field, value in (("config.json", "auto_map", {}),
                                  ("tokenizer_config.json", "auto_map", {}),
                                  ("tokenizer_config.json", "tokenizer_class", "UnreviewedTokenizer"),
                                  ("tokenizer_config.json", "backend", "unreviewed")):
            changed = copy.deepcopy(original)
            changed[file][field] = value
            for name, document in changed.items():
                path = directory / name
                path.write_bytes(canonical(document))
                path.chmod(0o600)
            with self.subTest(file=file, field=field), self.assertRaises(self.r.RendererBindingError):
                self.r._verify_current_loader_metadata(directory)

    def test_unsupported_requests_fail(self):
        renderer = self.renderer()
        for extra in ({"chat_template_kwargs": {"enable_thinking": None}},
                      {"chat_template_kwargs": {"unreviewed": True}},
                      {"tools": [{"type": "function"}]}, {"model": "other"},
                      {"messages": [{"role": "system", "content": "x"}]}):
            with self.subTest(extra=extra), self.assertRaises(self.r.RendererRequestError):
                renderer.count(self.body(**extra))


if __name__ == "__main__":
    unittest.main()
