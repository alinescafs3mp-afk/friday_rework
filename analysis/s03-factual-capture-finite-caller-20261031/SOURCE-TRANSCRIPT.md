# Sanitized S03 source excerpts

NONEXECUTABLE PUBLICATION TRANSCRIPT. Incomplete line-numbered text only; no module, imports, runnable control, private input or live authority. Omitted source remains private and hash-pinned. Two exact request/input constants are replaced explicitly below. No other selected code token is changed. Source line numbers refer to the frozen original named in each section.

## Accepted b218 tester: explicit optional output

Optionality is explicit and singleton-only. This is metadata validation, not workbook or answer semantics.

Original lines 729–732:

```text
00729 | def ordinary_optional_xlsx_output(value):
00730 |     # Explicit singleton opt-in. Historical two-key output descriptors stay required.
00731 |     return (isinstance(value, dict) and set(value) == {'filename', 'mime_type', 'required'}
00732 |             and value['required'] is False and value['mime_type'] == UPLOAD_TYPES['xlsx'])
```

Original lines 760–772:

```text
00760 | def ordinary_document_output_failures(output, documents):
00761 |     outputs = ordinary_document_outputs(output)
00762 |     if not outputs:
00763 |         return []
00764 |     if ordinary_optional_xlsx_output(output) and not documents:
00765 |         return []  # Text clarification is valid evidence; semantic review stays mandatory.
00766 |     if len(documents) != len(outputs):
00767 |         return ['EXPECTED_DOCUMENT_MISSING']
00768 |     if len(outputs) == 1:
00769 |         actual = documents[0].get('advertised_document', {})
00770 |         return [] if (actual.get('mime_type') == outputs[0]['mime_type']
00771 |                       and (outputs[0]['filename'] is None
00772 |                            or actual.get('file_name') == outputs[0]['filename'])) else ['EXPECTED_DOCUMENT_METADATA_MISMATCH']
```

Original lines 849–855:

```text
00849 | def ordinary_document_response_failures(output, observations):
00850 |     documents = [o for o in observations if o.get('kind') == 'document']
00851 |     failures = ordinary_document_output_failures(output, documents)
00852 |     if ((output is None or (ordinary_optional_xlsx_output(output) and not documents))
00853 |             and not any(o.get('kind') == 'reply_text' for o in observations)):
00854 |         failures.insert(0, 'EXPECTED_TEXT_MISSING')
00855 |     return failures
```

## Accepted b218 tester: exact factual scope

The request and input digest literals are withheld. Equality, MIME, type, document-count and fixed-window restrictions are retained in the transcript. The retained-source branch remains subject to independent admission/custody checks; this excerpt grants no authority.

Original lines 781–814:

```text
00781 | def ordinary_s03_factual_text_capture(spec, step, expected, message, text):
00782 |     """Capture exact protected S03 text as facts, never classify its semantics.
00783 | 
00784 |     Admission independently authenticates this task, fresh input or closed source,
00785 |     and full180 custody. A refusal marker is preserved in the receipt for external
00786 |     review. Words in received data do not grant execution rights or semantic PASS.
00787 |     """
00788 |     request = '<EXACT_PRIVATE_REQUEST_WITHHELD>'
00789 |     input_sha = '<EXACT_PRIVATE_INPUT_DIGEST_WITHHELD>'
00790 |     if (not isinstance(spec, dict) or spec.get('kind') != 'ordinary-document-task'
00791 |             or spec.get('request') != request
00792 |             or not ordinary_optional_xlsx_output(spec.get('output'))
00793 |             or spec['output']['filename'] is not None
00794 |             or not isinstance(step, dict) or not reply_capture(expected)
00795 |             or type(expected.get('max_documents')) is not int or expected['max_documents'] != 1
00796 |             or expected.get('window_seconds') != 180
00797 |             or 'document' in message or not isinstance(text, str) or not text.strip()):
00798 |         return False
00799 |     upload = step.get('input')
00800 |     reference = spec.get('source_reference')
00801 |     fresh = (isinstance(upload, dict) and reference is None
00802 |              and upload.get('sha256') == input_sha and upload.get('caption') == request
00803 |              and upload.get('mime_type') == UPLOAD_TYPES['xlsx'])
00804 |     retained = (upload is None and step.get('request') == request
00805 |                 and isinstance(reference, dict)
00806 |                 and set(reference) == {'run_id', 'run_sha256', 'input_sha256'}
00807 |                 and reference.get('input_sha256') == input_sha
00808 |                 and isinstance(reference.get('run_id'), str)
00809 |                 and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', reference['run_id']) is not None
00810 |                 and isinstance(reference.get('run_sha256'), str)
00811 |                 and re.fullmatch('[a-f0-9]{64}', reference['run_sha256']) is not None)
00812 |     if not (fresh or retained):
00813 |         return False
00814 |     return True
```

## Accepted b218 tester: ungraded receipt and refusal capture

The exact reply binding, ungraded receipt, bounded message/text limits and output-contract status are separate from semantic acceptance.

Original lines 11240–11248:

```text
11240 |                 if not self.continuation_document_match(run, message):
11241 |                     raise Refused('Wire-nonceless text receipt requires exact reply to admitted request')
11242 |                 receipt['response_binding'] = 'EXACT_REPLY_TO_REQUEST_UNGRADED'
11243 |                 receipt['reply_to_message_id'] = message['reply_to_message']['message_id']
11244 |             if ordinary_s03_factual_text_capture(admitted[0]['new_task'],
11245 |                     run['scenario']['steps'][run['step']],
11246 |                     run['scenario']['steps'][run['step']]['observe'], message, text):
11247 |                 receipt['text_interpretation'] = 'SEMANTIC_REVIEW_REQUIRED'
11248 |                 receipt['refusal_marker_observed'] = bool(REFUSAL.search(text))
```

Original lines 11509–11525:

```text
11509 |             s03_factual_text = (reply and admitted is not None
11510 |                 and ordinary_s03_factual_text_capture(admitted[0]['new_task'],
11511 |                     run['scenario']['steps'][run['step']], expected, message, text))
11512 |             if explicit_task_refusal(text) and not (settings_text or memory_text or unreadable_text or ambiguous_join_text or s03_factual_text):
11513 |                 raise Refused('Explicit refusal received; no paraphrase/retry')
11514 |             norm = ' '.join(text.casefold().split())
11515 |             run['repeat_count'] = run['repeat_count'] + 1 if norm == run['last_text'] else 0
11516 |             run['last_text'] = norm
11517 |             if run['repeat_count'] >= 2:
11518 |                 raise Refused('Repeated no-progress response; stop')
11519 |             if reply:
11520 |                 if sum(o.get('kind') in ('reply_text', 'document') for o in run['observations']) >= expected['max_messages']:
11521 |                     raise Refused('Bounded reply message budget exceeded; raw update retained')
11522 |                 if len(text) > expected['max_text_chars']:
11523 |                     raise Refused('Bounded reply text budget exceeded; raw update retained')
11524 |                 run['observations'].append(self.keep_text(run, message, update))
11525 |                 run.update(reply_text_acceptance='RECEIVED_UNGRADED', acceptance='NOT_ESTABLISHED')
```

Original lines 11747–11758:

```text
11747 |                     if reply:
11748 |                         documents = [o for o in run['observations'] if o.get('kind') == 'document']
11749 |                         run.update(capture_window_complete=True,
11750 |                                    reply_outcome='RECEIVED_UNGRADED' if run['observations'] else 'NO_RESPONSE_UNVERIFIED',
11751 |                                    artifact_acceptance='RECEIVED_UNGRADED' if documents else 'NOT_VERIFIED',
11752 |                                    acceptance='NOT_ESTABLISHED')
11753 |                     admitted=self.continuation_receipt(run)
11754 |                     if admitted is not None and admitted[0]['new_task']['kind']=='ordinary-document-task':
11755 |                         output=admitted[0]['new_task']['output']
11756 |                         failures=ordinary_document_response_failures(output, run['observations'])
11757 |                         run['ordinary_output_contract']=dict(status='FAIL' if failures else 'RECEIVED_UNGRADED',reason_codes=failures)
11758 |                     self.save(run)
```

## Proposed caller repair: strict JSON comparison

The repair changes equality at source acceptance and actual tester qualification joins; only the source-acceptance fragment is shown. Comparing encoded JSON distinguishes true from 1 and false from 0. This is an unaccepted source-only reviewer repair at the publication boundary.

Original lines 12–13:

```text
00012 | def exact_json(left,right):
00013 |     return json.dumps(left,sort_keys=True,allow_nan=False)==json.dumps(right,sort_keys=True,allow_nan=False)
```

Original lines 41–43:

```text
00041 |     b.need(exact_json(b.document(value['consumer_source_acceptance']),dict(schema='frw.Root.s03-source112-finite-caller-source-accepted.v1',operator='Root',accepted=True,
00042 |         source_only=True,package=package_ref,canonical_consumer=canonical,final_source=pkg['future_consumer_source'],strict_guard_unchanged=True,runtime_or_semantic_acceptance=False)),
00043 |         'S03_Root_whole_source_review_UNBOUND')
```

## Proposed caller repair: same-response review join

The compared review and expected document remain private; the excerpt contains only the equality change and refusal code, with no semantic oracle.

Original lines 53–54:

```text
00053 |     contract.need(contract.enc(reviewed)==contract.enc(expected),
00054 |         'S03_exact_same_response_private_semantic_review_required')
```

## Proposed caller repair: finite binding and local authority

The protected binding is compared by encoding before referenced current/source/qualification/priority/predecessor documents are rechecked.

Original lines 81–85:

```text
00081 | def validate_binding(runner,plan,ref):
00082 |     value=runner.ordinary_upgrade_reference(ref);need(enc(value)==enc(binding(plan)),'S03_exact_current_finite_binding_required')
00083 |     for n in ('current112_bindings','current_boundary','consumer_source_acceptance','tester_qualification','priority_authority','predecessor_closure'):
00084 |         runner.ordinary_upgrade_reference(value[n])
00085 |     PREDECESSOR.validate();return value
```

## Proposed caller repair: ordinary authority and live prerequisites

This redundant local authority join now matches the already strict lower canonical authority behavior. No new live right follows from the source excerpt.

Original lines 64–71:

```text
00064 |         def check_admission_current(self,runner,plan,*,receiving):
00065 |             k.validate_binding(runner,plan,self.binding_ref)
00066 |             path=runner.store.root/'reconciliations'/('ordinary-'+k.sha(k.enc(plan)))/'ROOT-AUTHORITY.json'
00067 |             value=self.consumer.json.loads(self.consumer.safe_read(path),object_pairs_hook=self.consumer.unique_object)
00068 |             k.need(k.enc(value)==k.enc(k.authority(plan)),'S03_exact_canonical_ordinary_v1_authority_required')
00069 |             self.binding.source_checked();self.binding.writer_authority();self.binding.role();self.binding.retained_cas()
00070 |             if not receiving:
00071 |                 k.PREDECESSOR.head(runner,self.consumer,plan['predecessor'],plan,False)
```

