"""New stdlib controls for exact excerpts; no product imports or effects.

Run: python3 -B test_provider_alias_excerpt.py
All module graphs, source rows and paths below are synthetic in-memory objects.
"""

import copy
import hashlib
import types
import unittest

import provider_alias_excerpt as subject


class AliasControls(unittest.TestCase):
    def setUp(self):
        self.original = subject._NATIVE_PROVIDER_BUNDLED_ROOTS
        self.digest = hashlib.sha256(b"synthetic root source").hexdigest()
        self.pin = {"directory": "sample-provider", "bytes": 21,
                    "mode": "100644", "sha256": self.digest}
        subject._NATIVE_PROVIDER_BUNDLED_ROOTS = {"sample_provider": self.pin}
        self.root = "plugins/model-providers/sample-provider"
        self.files = {self.root + "/__init__.py": {
            key: self.pin[key] for key in ("bytes", "mode", "sha256")}}

    def tearDown(self):
        subject._NATIVE_PROVIDER_BUNDLED_ROOTS = self.original

    def resolve(self, name="sample_provider", package=True, files=None):
        return subject._native_provider_alias_relative(
            "plugins.model_providers." + name, package,
            self.files if files is None else files)

    def reject(self, reason, name="sample_provider", package=True, files=None):
        with self.assertRaisesRegex(ValueError, "^root_project_only_" + reason + "$"):
            self.resolve(name, package, files)

    def test_hyphenated_package_maps_to_receipt_directory(self):
        self.assertEqual(self.resolve(), self.root + "/__init__.py")

    def test_descendant_module_and_package_preserve_components(self):
        for suffix, package, ending in (("client", False, "client.py"),
                                        ("nested", True, "nested/__init__.py"),
                                        ("nested.codec", False, "nested/codec.py")):
            with self.subTest(suffix=suffix, package=package):
                path = self.root + "/" + ending
                files = copy.deepcopy(self.files)
                files[path] = {"mode": "100644", "bytes": 0,
                               "sha256": hashlib.sha256(b"").hexdigest()}
                self.assertEqual(self.resolve("sample_provider." + suffix, package, files), path)

    def test_unrelated_namespace_is_not_claimed(self):
        for name in ("plugins.other", "plugins.model_providers", "tools.model_providers.x"):
            with self.subTest(name=name):
                self.assertIsNone(subject._native_provider_alias_relative(name, False, {}))

    def test_unknown_malformed_or_nonpackage_root_is_refused(self):
        for name, package in (("unlisted", True), ("", True),
                              ("sample_provider", False), ("sample_provider.", False),
                              ("sample_provider.bad-name", False),
                              ("sample_provider.0name", False),
                              ("sample_provider..client", False)):
            with self.subTest(name=name, package=package):
                self.reject("owned_native_provider_alias_name_refused", name, package)

    def test_normalization_collision_is_refused_even_with_identical_rows(self):
        files = copy.deepcopy(self.files)
        files["plugins/model-providers/sample_provider/__init__.py"] = dict(
            files[self.root + "/__init__.py"])
        self.reject("owned_native_provider_alias_ambiguous_or_foreign", files=files)

    def test_missing_root_and_foreign_normalized_directory_are_refused(self):
        self.reject("owned_native_provider_alias_ambiguous_or_foreign", files={})
        files = {"plugins/model-providers/sample_provider/__init__.py":
                 self.files[self.root + "/__init__.py"]}
        self.reject("owned_native_provider_alias_ambiguous_or_foreign", files=files)

    def test_nested_and_nonpackage_entries_do_not_create_root_ambiguity(self):
        files = copy.deepcopy(self.files)
        files["plugins/model-providers/sample_provider/child/__init__.py"] = {}
        files["plugins/model-providers/sample_provider.py"] = {}
        files[7] = {}
        self.assertEqual(self.resolve(files=files), self.root + "/__init__.py")

    def test_root_row_requires_exact_pin(self):
        for field, value in (("sha256", hashlib.sha256(b"foreign").hexdigest()),
                             ("bytes", 22), ("mode", "100755")):
            with self.subTest(field=field):
                files = copy.deepcopy(self.files)
                files[self.root + "/__init__.py"][field] = value
                self.reject("owned_native_provider_alias_root_not_pinned", files=files)
        files = {self.root + "/__init__.py": []}
        self.reject("owned_native_provider_alias_root_not_pinned", files=files)

    def test_missing_descendant_does_not_fall_back_to_another_path(self):
        self.reject("owned_native_provider_alias_descendant_not_pinned",
                    "sample_provider.client", False)

    def test_descendant_row_shape_and_digest_are_refused(self):
        path = self.root + "/client.py"
        good = {"mode": "100644", "bytes": 0,
                "sha256": hashlib.sha256(b"").hexdigest()}
        bad_rows = [None, [], {}, dict(good, mode="100755"),
                    dict(good, bytes=-1), dict(good, bytes=True),
                    dict(good, bytes="0"), dict(good, sha256=None),
                    dict(good, sha256="a" * 63), dict(good, sha256="G" * 64),
                    dict(good, sha256="A" * 64)]
        for index, row in enumerate(bad_rows):
            with self.subTest(row=index):
                files = copy.deepcopy(self.files)
                files[path] = row
                self.reject("owned_native_provider_alias_descendant_not_pinned",
                            "sample_provider.client", False, files)

    def test_explicit_source_pin_table_is_required(self):
        subject._NATIVE_PROVIDER_BUNDLED_ROOTS = {}
        self.reject("owned_native_provider_alias_name_refused")


class UnwindControls(unittest.TestCase):
    def setUp(self):
        self.original_sys = subject.sys
        self.unrelated = object()
        self.fake = types.SimpleNamespace(
            modules={"unrelated": self.unrelated},
            path=["synthetic-base"], dont_write_bytecode=False)
        subject.sys = self.fake
        self.known = {}
        self.authenticated = []

    def tearDown(self):
        subject.sys = self.original_sys

    def authenticate(self, name, module):
        if self.known.get(name) is not module:
            raise ValueError("synthetic_authentication_refused")
        self.authenticated.append(name)

    def begin(self):
        guard = subject._OwnedModuleUnwind(self.authenticate)
        self.fake.dont_write_bytecode = True
        return guard

    def add(self, name, package=False):
        module = types.ModuleType(name)
        module.__file__ = "synthetic-source/" + name.replace(".", "/") + ".py"
        module.__package__ = name if package else name.rpartition(".")[0]
        module.__loader__ = object()
        module.__spec__ = types.SimpleNamespace(
            name=name, origin=module.__file__,
            submodule_search_locations=["synthetic-package"] if package else None)
        if package:
            module.__path__ = ["synthetic-package"]
        self.fake.modules[name] = module
        self.known[name] = module
        parent, _, child = name.rpartition(".")
        if parent in self.fake.modules:
            setattr(self.fake.modules[parent], child, module)
        return module

    def assert_refused_without_cleanup(self, guard, reason):
        modules_object = self.fake.modules
        path_object = self.fake.path
        modules_before = dict(modules_object)
        path_before = list(path_object)
        bytecode_before = self.fake.dont_write_bytecode
        with self.assertRaisesRegex(ValueError, "^" + reason + "$"):
            guard.close()
        self.assertIs(self.fake.modules, modules_object)
        self.assertEqual(self.fake.modules, modules_before)
        self.assertIs(self.fake.path, path_object)
        self.assertEqual(self.fake.path, path_before)
        self.assertIs(self.fake.dont_write_bytecode, bytecode_before)

    def test_cold_owned_graph_unwinds_and_preserves_unrelated_module(self):
        original_path = self.fake.path
        guard = self.begin()
        self.add("plugins", True)
        self.add("plugins.model_providers", True)
        self.add("plugins.model_providers.sample_provider", True)
        self.add("plugins.model_providers.sample_provider.client")
        self.fake.path.insert(0, "synthetic-inserted")
        guard.expected_paths.append(list(self.fake.path))
        guard.checkpoint()
        guard.close()
        self.assertEqual(self.fake.modules, {"unrelated": self.unrelated})
        self.assertIs(self.fake.path, original_path)
        self.assertEqual(self.fake.path, ["synthetic-base"])
        self.assertFalse(self.fake.dont_write_bytecode)
        self.assertEqual(set(self.authenticated), set(self.known))

    def test_two_clean_cycles_leave_the_same_fake_state(self):
        for _ in range(2):
            guard = self.begin()
            self.add("plugins", True)
            guard.close()
            self.assertEqual(self.fake.modules, {"unrelated": self.unrelated})
            self.assertFalse(self.fake.dont_write_bytecode)

    def test_empty_graph_and_original_bytecode_policy_are_restored(self):
        self.fake.dont_write_bytecode = True
        guard = self.begin()
        guard.close()
        self.assertTrue(self.fake.dont_write_bytecode)

    def test_preexisting_owned_namespace_is_never_evicted(self):
        module = self.add("plugins", True)
        with self.assertRaisesRegex(ValueError, "owned_unwind_requires_cold_namespaces$"):
            subject._OwnedModuleUnwind(self.authenticate)
        self.assertIs(self.fake.modules["plugins"], module)
        self.assertFalse(self.fake.dont_write_bytecode)

    def test_similar_unrelated_names_are_preserved(self):
        self.fake.modules["plugins_other"] = object()
        self.fake.modules["toolshed"] = object()
        before = dict(self.fake.modules)
        guard = self.begin()
        guard.close()
        self.assertEqual(self.fake.modules, before)

    def test_modules_container_replacement_is_refused(self):
        guard = self.begin()
        self.fake.modules = dict(self.fake.modules)
        self.assert_refused_without_cleanup(guard, "root_project_only_owned_global_container_identity_changed")

    def test_path_container_replacement_is_refused(self):
        guard = self.begin()
        self.fake.path = list(self.fake.path)
        self.assert_refused_without_cleanup(guard, "root_project_only_owned_global_container_identity_changed")

    def test_unexpected_path_content_is_refused(self):
        guard = self.begin()
        self.add("plugins", True)
        self.fake.path.append("unexpected")
        self.assert_refused_without_cleanup(guard, "root_project_only_owned_sys_path_CAS_changed")

    def test_disabled_bytecode_policy_is_refused(self):
        guard = self.begin()
        self.add("plugins", True)
        self.fake.dont_write_bytecode = False
        self.assert_refused_without_cleanup(guard, "root_project_only_owned_bytecode_policy_changed")

    def test_removed_observed_module_is_refused(self):
        guard = self.begin()
        self.add("plugins", True)
        guard.checkpoint()
        del self.fake.modules["plugins"]
        self.assert_refused_without_cleanup(guard, "root_project_only_owned_module_removed_before_unwind")

    def test_observed_module_replacement_is_refused(self):
        guard = self.begin()
        self.add("plugins", True)
        guard.checkpoint()
        self.fake.modules["plugins"] = types.ModuleType("plugins")
        self.assert_refused_without_cleanup(guard, "root_project_only_owned_module_identity_or_namespace_changed")

    def test_observed_module_signature_changes_are_refused(self):
        mutations = (
            lambda module: setattr(module, "__file__", "changed"),
            lambda module: setattr(module.__spec__, "origin", "changed"),
            lambda module: setattr(module, "__spec__", copy.copy(module.__spec__)),
            lambda module: setattr(module, "__loader__", object()),
            lambda module: setattr(module, "__package__", "changed"),
            lambda module: module.__path__.append("changed"),
            lambda module: module.__spec__.submodule_search_locations.append("changed"))
        for index, mutate in enumerate(mutations):
            with self.subTest(signature_field=index):
                self.fake.modules = {"unrelated": self.unrelated}
                guard = self.begin()
                module = self.add("plugins", True)
                guard.checkpoint()
                mutate(module)
                self.assert_refused_without_cleanup(guard, "root_project_only_owned_module_identity_or_namespace_changed")

    def test_wrong_parent_child_object_is_refused(self):
        guard = self.begin()
        parent = self.add("plugins", True)
        self.add("plugins.child")
        parent.child = object()
        self.assert_refused_without_cleanup(guard, "root_project_only_owned_parent_child_identity_changed")

    def test_failed_source_authentication_does_not_remove_modules(self):
        guard = self.begin()
        self.add("plugins", True)
        self.known.clear()
        self.assert_refused_without_cleanup(guard, "synthetic_authentication_refused")

    def test_final_graph_addition_during_authentication_is_refused(self):
        guard = self.begin()
        self.add("plugins", True)
        def authenticate_and_insert(name, module):
            self.authenticate(name, module)
            if "plugins.late" not in self.fake.modules:
                self.add("plugins.late")
        guard.authenticate = authenticate_and_insert
        with self.assertRaisesRegex(ValueError, "owned_module_final_CAS_changed$"):
            guard.close()
        self.assertIn("plugins", self.fake.modules)
        self.assertIn("plugins.late", self.fake.modules)
        self.assertEqual(self.fake.path, ["synthetic-base"])
        self.assertTrue(self.fake.dont_write_bytecode)


if __name__ == "__main__":
    unittest.main(verbosity=2)
