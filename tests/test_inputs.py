"""Real filesystem staging joined to receive-time native content receipts.

Native transport provenance is tested in Hermes; these fixtures are host inputs,
not demonstrations that a model-supplied receipt confers authority.
"""
import copy
import hashlib
import importlib.util
from pathlib import Path
import stat
import sys
import tempfile
import unittest

root = Path(__file__).resolve().parents[1] / "plugins/friday_rework"
spec = importlib.util.spec_from_file_location("friday_input_test", root / "__init__.py",
                                            submodule_search_locations=[str(root)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
from friday_input_test.admission import _snapshot
from friday_input_test.artifacts import ArtifactError
from friday_input_test.inputs import stage_inputs


class InputTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.cache, self.stage = self.root / "cache", self.root / "stage"
        self.cache.mkdir(mode=0o700)
        self.stage.mkdir(mode=0o700)
        self.payload = b"code and data\x00\xff\n"
        self.source = self.cache / "source.py"
        self.source.write_bytes(self.payload)
        self.proof = {"platform": "telegram", "session_key": "session-key", "source_profile": "",
                      "transport_profile": "default", "runtime_profile": "default",
                      "message": dict(bot_id="9001", user_id="111", chat_id="-1001", thread_id="17",
                                      message_id="501", platform_update_id="701",
                                      reply_to_message_id="499", media=[])}
        self.media = dict(local_reference=str(self.source), mime_type="text/x-python",
                          origin=dict(bot_id="9001", chat_id="-1001", thread_id="17", message_id="501",
                                      file_id="native-id", file_unique_id="unique", declared_bytes=1),
                          content=dict(size_bytes=len(self.payload), sha256=hashlib.sha256(self.payload).hexdigest()))
        self.proof["message"]["media"] = [self.media]

    def stage_inputs(self, **changes):
        args = dict(matched_ingress=self.proof, admitted_reference="receipt:native-call",
                    cache_roots=(self.cache,), staging_root=self.stage, worker_input_root="/job/inputs",
                    max_file_bytes=64, max_total_bytes=128)
        args.update(changes)
        return stage_inputs(**args)

    def test_exact_received_bytes_own_and_reply(self):
        for message in ("501", "499"):
            with self.subTest(message=message):
                self.media["origin"]["message_id"] = message
                (item,) = self.stage_inputs()
                staged = Path(item.host_path)
                self.assertEqual(staged.read_bytes(), self.payload)
                self.assertEqual(staged.parent, self.stage)
                self.assertEqual(item.worker_path, "/job/inputs/" + staged.name)
                self.assertEqual(item.sha256, self.media["content"]["sha256"])
                self.assertEqual(item.size_bytes, len(self.payload))
                self.assertEqual(item.receipt_reference, "receipt:native-call")
                self.assertEqual(stat.S_IMODE(staged.stat().st_mode), 0o400)
        self.assertEqual(self.source.read_bytes(), self.payload)

    def test_legacy_receipt_is_readable_but_not_byte_authority(self):
        del self.media["content"]
        self.assertEqual(_snapshot(self.proof), self.proof)
        with self.assertRaisesRegex(ArtifactError, "unproved_input_bytes"):
            self.stage_inputs()
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_unproven_ambiguous_origin_and_foreign_message(self):
        for origin in (None, {**self.media["origin"], "message_id": "500"}):
            with self.subTest(origin=origin):
                proof = copy.deepcopy(self.proof)
                proof["message"]["media"][0]["origin"] = origin
                with self.assertRaises(ArtifactError):
                    self.stage_inputs(matched_ingress=proof)
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_foreign_bot_chat_topic_rejected(self):
        for field in ("bot_id", "chat_id", "thread_id"):
            with self.subTest(field=field):
                proof = copy.deepcopy(self.proof)
                proof["message"]["media"][0]["origin"][field] = "other"
                with self.assertRaisesRegex(ValueError, "foreign_input_origin"):
                    self.stage_inputs(matched_ingress=proof)

    def test_same_size_cache_mutation_cannot_become_current_authority(self):
        self.source.write_bytes(b"X" * len(self.payload))
        with self.assertRaisesRegex(ArtifactError, "input_bytes_changed_since_receive"):
            self.stage_inputs()
        # A retained private copy is evidence, never a returned worker grant.
        self.assertTrue(all(stat.S_IMODE(p.stat().st_mode) == 0o400 for p in self.stage.iterdir()))

    def test_cache_growth_and_shrink_refuse_mapping(self):
        for value in (b"x", self.payload + b"tail", b"x" * 65):
            with self.subTest(size=len(value)):
                self.source.write_bytes(value)
                with self.assertRaises(ArtifactError):
                    self.stage_inputs()

    def test_declared_remote_size_is_not_actual_byte_count(self):
        self.media["origin"]["declared_bytes"] = 0
        self.assertEqual(self.stage_inputs()[0].size_bytes, len(self.payload))

    def test_missing_content_shape_and_types(self):
        values = [None, {}, {"size_bytes": len(self.payload)},
                  {**self.media["content"], "extra": "untrusted"},
                  *({**self.media["content"], "size_bytes": x} for x in (-1, True, "12", 1.0)),
                  *({**self.media["content"], "sha256": x} for x in (None, 1, "a" * 63, "F" * 64, "z" * 64))]
        for value in values:
            with self.subTest(value=value):
                proof = copy.deepcopy(self.proof)
                proof["message"]["media"][0]["content"] = value
                with self.assertRaisesRegex(ValueError, "invalid_ingress_content"):
                    self.stage_inputs(matched_ingress=proof)
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_actual_per_file_and_aggregate_limits_precede_any_copy(self):
        self.proof["message"]["media"].append(copy.deepcopy(self.media))
        for limits in ({"max_file_bytes": len(self.payload) - 1},
                       {"max_total_bytes": len(self.payload) * 2 - 1}):
            with self.subTest(limits=limits), self.assertRaisesRegex(ArtifactError, "input_too_large"):
                self.stage_inputs(**limits)
        self.assertEqual(list(self.stage.iterdir()), [])
        self.assertEqual(len(self.stage_inputs(max_total_bytes=2 * len(self.payload))), 2)

    def test_all_metadata_preflighted_before_copying_first_file(self):
        bad = copy.deepcopy(self.media)
        bad["origin"] = None
        self.proof["message"]["media"].append(bad)
        with self.assertRaises(ArtifactError):
            self.stage_inputs()
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_empty_input_has_no_stub(self):
        self.proof["message"]["media"] = []
        self.assertEqual(self.stage_inputs(), ())
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_duplicate_filenames_get_distinct_stable_paths(self):
        other = self.cache / "reply"
        other.mkdir()
        (other / self.source.name).write_bytes(self.payload)
        second = copy.deepcopy(self.media)
        second["local_reference"] = str(other / self.source.name)
        second["origin"]["message_id"] = "499"
        self.proof["message"]["media"].append(second)
        result = self.stage_inputs()
        self.assertEqual(len(result), 2)
        self.assertNotEqual(result[0].host_path, result[1].host_path)

    def test_no_unrelated_paths_or_traversal_or_symlinks(self):
        outside = self.root / "outside.py"
        outside.write_bytes(self.payload)
        link = self.cache / "link.py"
        link.symlink_to(outside)
        for source in (str(outside), "source.py", str(self.cache / ".." / "outside.py"), str(link)):
            with self.subTest(source=source):
                self.media["local_reference"] = source
                with self.assertRaises((ArtifactError, OSError)):
                    self.stage_inputs()
        self.assertEqual(list(self.stage.iterdir()), [])

    def test_empty_relative_overlapping_and_symlink_roots_refused(self):
        link = self.root / "cache-alias"
        link.symlink_to(self.cache)
        for roots in ((), (Path("cache"),), (self.root, self.cache), (link,), (self.cache, self.cache)):
            with self.subTest(roots=roots), self.assertRaises(ArtifactError):
                self.stage_inputs(cache_roots=roots)

    def test_worker_mapping_cannot_escape_or_be_ambiguous(self):
        for root in (None, "", "/", "inputs", "/job/../inputs", "/job/./inputs", "/job//inputs",
                     "//job/inputs", "/job/inputs/", "/job/\x00inputs"):
            with self.subTest(root=root), self.assertRaises(ArtifactError):
                self.stage_inputs(worker_input_root=root)

    def test_invalid_limits_and_receipt_labels(self):
        for value in (True, 0, -1, "64", 1.0, None):
            for key in ("max_file_bytes", "max_total_bytes"):
                with self.subTest(key=key, value=value), self.assertRaises(ArtifactError):
                    self.stage_inputs(**{key: value})
        for value in (None, "", "  ", "x\x00", "x" * 2049):
            with self.subTest(receipt=value), self.assertRaises(ArtifactError):
                self.stage_inputs(admitted_reference=value)


if __name__ == "__main__":
    unittest.main()
