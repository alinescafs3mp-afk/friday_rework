# Rejected B138 source excerpts

NONEXECUTABLE PUBLICATION TRANSCRIPT. This file contains incomplete, line-numbered text excerpts of rejected code. It supplies no module, imports, runnable control, install target or live authority. Do not install, invoke or treat it as a repair. The original source is retained privately by exact hash. Only the private peer literal is changed inside the selected code; omitted source is identified by the line ranges. Code-level keys called input/oracle/caption contain no private values here.

## B138-V1 — verify_units.py

Workbook typing is checked, but the consumed worksheet path is parsed without resolving its content type.

Original lines 147–166:

```text
00147 |     def _validate_opc(self, archive, names):
00148 |         required = {"[Content_Types].xml", "_rels/.rels", "xl/workbook.xml", "xl/_rels/workbook.xml.rels"}
00149 |         if not required <= names:
00150 |             reject("INVALID_XLSX_STRUCTURE", "Required OPC workbook parts are missing", missing=sorted(required - names))
00151 |         content_ns = "http://schemas.openxmlformats.org/package/2006/content-types"
00152 |         content = self._xml(archive, "[Content_Types].xml", f"{{{content_ns}}}Types")
00153 |         overrides = {}
00154 |         for node in content.findall(f"{{{content_ns}}}Override"):
00155 |             part = node.get("PartName")
00156 |             if not part or part in overrides:
00157 |                 reject("INVALID_XLSX_STRUCTURE", "Missing or duplicate OPC content-type override", part=part)
00158 |             overrides[part] = node.get("ContentType")
00159 |         expected_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"
00160 |         if overrides.get("/xl/workbook.xml") != expected_type:
00161 |             reject("INVALID_XLSX_STRUCTURE", "OPC workbook content type is not an ordinary XLSX workbook")
00162 |         package = self._xml(archive, "_rels/.rels", f"{{{PKG_REL_NS}}}Relationships")
00163 |         office_type = f"{DOC_REL_NS}/officeDocument"
00164 |         office = [node for node in package.findall(f"{{{PKG_REL_NS}}}Relationship") if node.get("Type") == office_type]
00165 |         if len(office) != 1 or office[0].get("Target", "").lstrip("/") != "xl/workbook.xml":
00166 |             reject("INVALID_XLSX_STRUCTURE", "Package must have one exact XLSX workbook relationship")
```

Original lines 196–205:

```text
00196 |             target = targets.get(relation_id)
00197 |             if not target or types.get(relation_id) != f"{DOC_REL_NS}/worksheet":
00198 |                 reject("INVALID_XLSX_STRUCTURE", "Worksheet relationship is missing or has the wrong type", sheet=name)
00199 |             if target.startswith("/"):
00200 |                 member = target.lstrip("/")
00201 |             else:
00202 |                 member = posixpath.normpath(posixpath.join("xl", target))
00203 |             if member.startswith("../") or member not in names or not member.startswith("xl/worksheets/"):
00204 |                 reject("INVALID_XLSX_STRUCTURE", "Unsafe or missing worksheet target", sheet=name, target=target)
00205 |             root = self._xml(archive, member, f"{{{MAIN_NS}}}worksheet")
```

## B138-V2 — verify_units.py

The declaration scan inspects raw bytes before passing the original encoding to the parser.

Original lines 134–144:

```text
00134 |     def _xml(self, archive, name, expected_root=None):
00135 |         data = archive.read(name)
00136 |         upper = data.upper()
00137 |         if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
00138 |             reject("UNSAFE_XML", "DTD and entity declarations are refused", member=name)
00139 |         try:
00140 |             root = ET.fromstring(data)
00141 |         except ET.ParseError as exc:
00142 |             reject("INVALID_XLSX_XML", "Malformed workbook XML", member=name, error=str(exc))
00143 |         if expected_root is not None and root.tag != expected_root:
00144 |             reject("INVALID_XLSX_STRUCTURE", "Unexpected XML root", member=name, expected=expected_root, actual=root.tag)
```

## B138-V3 — verify_units.py

Formula discovery and cell classification inspect only a cell-local formula element, not range output coverage.

Original lines 233–250:

```text
00233 |                     formula = cell.find(f"{{{MAIN_NS}}}f")
00234 |                     if formula is not None:
00235 |                         cached = cell.find(f"{{{MAIN_NS}}}v")
00236 |                         raw = None if cached is None else cached.text
00237 |                         numeric = False
00238 |                         if raw and cell.get("t") in (None, "n"):
00239 |                             try:
00240 |                                 numeric = Decimal(raw).is_finite()
00241 |                             except InvalidOperation:
00242 |                                 numeric = False
00243 |                         self.formulas.append({
00244 |                             "sheet": name,
00245 |                             "cell": reference,
00246 |                             "formula_text": formula.text or "",
00247 |                             "cached_raw": raw,
00248 |                             "cached_numeric_available": numeric,
00249 |                             "cache_used": False,
00250 |                         })
```

Original lines 254–264:

```text
00254 |     def cell(self, sheet, reference):
00255 |         if sheet not in self.sheets:
00256 |             reject("MISSING_SHEET", "Mapped worksheet is absent", sheet=sheet)
00257 |         reference = normalize_cell(reference)
00258 |         cell = self.sheets[sheet].get(reference)
00259 |         if cell is None:
00260 |             return {"kind": "missing", "raw": None, "value": None, "formula": False}
00261 |         formula = cell.find(f"{{{MAIN_NS}}}f") is not None
00262 |         kind = cell.get("t", "n")
00263 |         if kind not in ("n", "inlineStr", "s", "str", "b", "e", "d"):
00264 |             reject("INVALID_XLSX_STRUCTURE", "Unsupported or unknown XLSX cell type", sheet=sheet, cell=reference, actual_type=kind)
```

## B138-V4 — verify_units.py

The shared-strings part is selected by familiar path alone.

Original lines 168–172:

```text
00168 |     def _shared_strings(self, archive, names):
00169 |         if "xl/sharedStrings.xml" not in names:
00170 |             return []
00171 |         root = self._xml(archive, "xl/sharedStrings.xml", f"{{{MAIN_NS}}}sst")
00172 |         return ["".join(node.text or "" for node in item.findall(f".//{{{MAIN_NS}}}t")) for item in root]
```

## B138-V5 — verify_units.py

Digit-only lexical validation precedes an unbounded integer conversion.

Original lines 268–279:

```text
00268 |         if kind == "s":
00269 |             value_node = cell.find(f"{{{MAIN_NS}}}v")
00270 |             if value_node is None or value_node.text is None:
00271 |                 return {"kind": "missing", "raw": None, "value": None, "formula": formula}
00272 |             raw_index = value_node.text
00273 |             if not re.fullmatch(r"[0-9]+", raw_index):
00274 |                 reject("INVALID_XLSX_STRUCTURE", "Shared string index must be a nonnegative integer", sheet=sheet, cell=reference)
00275 |             index = int(raw_index)
00276 |             if index >= len(self.shared_strings):
00277 |                 reject("INVALID_XLSX_STRUCTURE", "Shared string index is out of bounds", sheet=sheet, cell=reference)
00278 |             value = self.shared_strings[index]
00279 |             return {"kind": "string", "raw": value, "value": value, "formula": formula}
```

## B138-C1 — root_s06.py

The FIRST_FILE predecessor is the old P03 proof; the closed currency QUESTION frontier is absent.

Original lines 39–42:

```text
00039 |     k.P03_PROOF=proof.Proof(k,b,pins,value['P03_cursor_sha256'])
00040 |     if value['stage']=='QUESTION':k.FIRST_PROOF=proof.Proof(k,b,pins,value['cursor_sha256'],first_stage_ref=value['first_stage_closure'])
00041 |     else:b.need(value['cursor_sha256']==value['P03_cursor_sha256'],'S06_first_current_cursor_must_be_P03_cursor')
00042 |     k.PREDECESSOR=k.FIRST_PROOF or k.P03_PROOF
```

## B138-C2 — root_s06.py

Package/provider, memo, input, setup and history work precede preparation timer creation.

Original lines 74–88:

```text
00074 |     pins=pkg['production_pins'];provider_pkg=json.loads(Path(pins['current112_package']['path']).read_bytes())
00075 |     # Package pin is verified before using the provider's pinned Current112 leaf.
00076 |     load_source=Path(pins['current112_package']['path']).read_bytes()
00077 |     if hashlib.sha256(load_source).hexdigest()!=pins['current112_package']['sha256']:raise ValueError('S06_Current112_package_changed')
00078 |     base=load(provider_pkg['files']['current112.py'],'_s06_existing_Current112');b=base.low()
00079 |     oldpkg=b.document(pins['historical_w10_package'])
00080 |     load(oldpkg['files']['preparation.py'],'_s06_existing_invocation_memo').Memo(b,immutable=[*files.values(),*pins.values(),*oldpkg['files'].values(),*provider_pkg['files'].values()]).install()
00081 |     for ref in [*files.values(),*pins.values()]:b.read(ref)
00082 |     value=b.document(a.inputs_ref);canonical=check_inputs(b,pkg,a.package_ref,value,base)
00083 |     c=base.load_raw(b.read(canonical),base.T,'_s06_actual_canonical_consumer')
00084 |     store=c.Store(base.S);runner=c.Runner(store,None)
00085 |     k,oldpkg,parent=setup(b,pkg,value,runner,c)
00086 |     foundation=b.document(pins['m11_foundation']);closure=load(foundation['files']['m11_closed.py'],'_s06_accepted_ancestry_closure').Proof(b,foundation['actual_closed_acceptance'])
00087 |     history=load(files['s06_history.py'],'_s06_exact_history').install(c,k,load,canonical['sha256'],closure,dict(files=parent['files'],historical_w10_history=oldpkg['files']['w10_history.py']))
00088 |     oldinputs=b.document(pins['historical_w10_inputs']);history.prepare_metadata(oldinputs['final_guard_binding'])
```

Original lines 93–96:

```text
00093 |     base.put(b,out/'ATTEMPT.json',dict(command=a.command,inputs=a.inputs_ref,no_send=True,no_admission=True,no_retry=True))
00094 |     stage='fresh_current112';dispatch=None;plan_ref=None;overall=time.monotonic()+90
00095 |     def expired(*_):raise RuntimeError('S06_preparation90_exhausted')
00096 |     previous=signal.signal(signal.SIGALRM,expired);signal.setitimer(signal.ITIMER_REAL,90)
```

## B138-C3 — s06_runtime.py

Only the runtime-plan hook is changed here.

Original lines 78–83:

```text
00078 |     def install(consumer,factory):
00079 |         k.need(not getattr(consumer,'_s06_finite_installed',False),'S06_adapter_once_per_fresh_process')
00080 |         old=consumer.s07_runtime_plan
00081 |         consumer.s07_runtime_plan=lambda plan:old(plan) or k.exact_future(plan)
00082 |         consumer.S07_RUNTIME_HOOK=factory;consumer._s06_finite_installed=True
00083 |     base.install_s06=install
```

## B138-C3 — canonical_material.py

The nearest exact material consumer remains bound to the historical currency variant. Caption is a source dictionary key only; no caption value is published.

Original lines 7935–7954:

```text
07935 |         grant = self.ordinary_upgrade_reference(reference)
07936 |         stage = grant.get('stage') if isinstance(grant,dict) else None
07937 |         upload = S06_INPUTS.get(stage)
07938 |         spec = plan['new_task']
07939 |         if (upload is None or plan.get('schema') != 'friday.tester.continue-closed-unknown.v2'
07940 |                 or plan['new_scenario']['steps'][0].get('input') != upload
07941 |                 or spec.get('kind') != 'ordinary-document-task'
07942 |                 or spec.get('request') != upload['caption']
07943 |                 or spec.get('source_reference') is not None or spec.get('output') is not None
07944 |                 or comparison.get('id') != plan['predecessor']['run_id']
07945 |                 or previous_plan.get('new_run_id') != comparison.get('id')
07946 |                 or 's05_finite' in plan or 'm12_budget' in plan):
07947 |             raise Refused('Exact S06 original, stage, natural caption and serial predecessor required')
07948 |         expected = dict(schema='frw.bot-tester.s06-original-input.v1',operator='Root',case='S-06',
07949 |             variant='currencies-RUB-USD-original-pair-v1',stage=stage,
07950 |             decision='ONE_DISTINCT_S06_STAGE_EXACT_ORIGINAL_INPUT',
07951 |             plan_sha256=digest(encoded(plan)),tester_sha256=digest(safe_read(__file__)),
07952 |             predecessor=plan['predecessor'],current_tuple=plan['current_tuple'],
07953 |             input=upload,request=upload['caption'],catalog_reference=S06_CATALOG,
07954 |             old_effects_and_clocks_preserved=True,old_send_replay_authorized=False,product_acceptance=False)
```

## B138-C4 — s06_predecessor.py

Artifact, receipt and input pins are checked, but the PASS report is not joined to the map/verifier/oracle pins. Omitted lines validate the map schema and group names; they do not bind that map to the report.

Original lines 30–36:

```text
00030 |     k.need(evidence['artifact']==artifact_ref and evidence['receipt']==receipt_ref
00031 |         and evidence['verifier']==pins['physical_units_verifier']and evidence['input']==pins['physical_units_input']
00032 |         and evidence['oracle']==pins['physical_units_oracle'],'S06_artifact_evidence_pin_mismatch')
00033 |     k.need(len(b.read(artifact_ref))==doc['bytes'],'S06_actual_artifact_bytes_changed')
00034 |     receipt=b.document(receipt_ref);mapping=b.document(evidence['map']);report=b.document(evidence['report'])
00035 |     for name in ('run_id','scenario_sha256','step','sent_message_id','sent_ids','request_body_sha256','kind','sha256','bytes','path','message_id','update_id','complete_artifact','artifact_acceptance'):
00036 |         k.need(receipt.get(name)==doc.get(name),'S06_receipt_observation_join_changed')
```

Original lines 40–45:

```text
00040 |     k.need(report.get('status')=='PASS_OFFLINE_ARTIFACT_SEMANTICS'and report.get('artifact_sha256')==doc['sha256']
00041 |         and report.get('input_sha256')==pins['physical_units_input']['sha256']and report.get('oracle_recomputed_from_raw_cells')is True
00042 |         and report.get('product_acceptance')=='NOT_RUN','S06_actual_artifact_verifier_report_required')
00043 |     validate_terminal(run,b.document(value['terminal']))
00044 |     k.INPUT_PATH=doc['path'];k.INPUT_SHA=doc['sha256'];k.ARTIFACT=copy.deepcopy(doc)
00045 |     return artifact_ref
```

## B138-C5 — s06_predecessor.py

Terminal validation uses flags and time; the later receive_inventory call omits terminal=True and never checks drain.complete.

Original lines 6–14:

```text
00006 | def validate_terminal(run,terminal):
00007 |     until=run.get('capture_until');completed=terminal.get('completed_at')if isinstance(terminal,dict)else None
00008 |     ok=(isinstance(terminal,dict)and terminal.get('kind')=='terminal_complete'
00009 |         and run.get('status')=='EVIDENCE_READY'and run.get('capture_window_complete')is True
00010 |         and type(until)in(int,float)and math.isfinite(until)and type(completed)in(int,float)
00011 |         and math.isfinite(completed)and completed>=until and terminal.get('receive_error')is None
00012 |         and terminal.get('eof')is not True)
00013 |     if not ok:raise ValueError('S06_genuine_terminal_full180_required')
00014 |     return True
```

Original lines 132–136:

```text
00132 |         if check_custody:
00133 |             names=('_serial_custody','_closed_text_predecessor','reply_run','legacy_run');saved={n:(hasattr(runner,n),getattr(runner,n,None))for n in names}
00134 |             try:
00135 |                 runner._serial_custody=True;runner._closed_text_predecessor=(run['id'],old)
00136 |                 runner.verify_reply_custody(run,cursor=cursor);runner.receive_inventory(run,cursor)
```

## B138-C6 — s06_contract.py

FIRST_FILE can observe one document while task.output remains None.

Original lines 37–40:

```text
00037 | def scenario():
00038 |     need(STAGE in STAGES and ANCESTOR is not None,'S06_stage_UNBOUND')
00039 |     observe=dict(mode='bounded_reply_capture',window_seconds=180,max_messages=16,max_text_chars=8000,max_documents=1 if STAGE=='FIRST_FILE'else 0,document_max_bytes=8388608)
00040 |     step=dict(input=copy.deepcopy(INPUT),observe=observe)if STAGE=='FIRST_FILE'else dict(request=REQUEST,observe=observe)
```

Original lines 48–50:

```text
00048 |     plan.update(schema='friday.tester.continue-closed-unknown.v2',operator='Root',action_id=action_id,new_run_id=run_id,new_scenario=scenario(),
00049 |         new_task=dict(kind='ordinary-document-task',nonce=nonce,request=REQUEST,source_reference=None,output=None),clock=copy.deepcopy(clock),current_tuple=dict(TUPLE),ack_timeout_seconds=10,
00050 |         acknowledgement='OLD_OUTCOME_UNKNOWN_NO_REPLAY_NEW_DISTINCT_EFFECT_AUTHORIZED',predecessor=copy.deepcopy(head))
```

Original lines 58–61:

```text
00058 |     task=plan['new_task'];old=PREDECESSOR.previous
00059 |     need(type(task)is dict and set(task)=={'kind','nonce','request','source_reference','output'}and task['kind']=='ordinary-document-task'
00060 |         and task['request']==REQUEST and task['source_reference']is None and task['output']is None
00061 |         and type(task['nonce'])is str and re.fullmatch('[a-f0-9]{32}',task['nonce'])is not None,'S06_original_natural_input_only_required')
```

## B138-C7 — s06_runtime.py

The adapter delegates to the unchanged lower native user-request method.

Original lines 37–41:

```text
00037 |             def native_user_request(self,run,user):
00038 |                 k.validate_plan_shape(consumer,self.plan)
00039 |                 k.need(run['scenario']==self.plan['new_scenario'] and run['scenario_sha256']==k.sha(k.enc(run['scenario'])),
00040 |                     'S06_exact_sent_document_scenario_required')
00041 |                 return lower['Live'].native_user_request(self,run,user)
```

## B138-C7 — native_correlation.py

The lower text branch requires a dict source_reference. The private peer literal on line 309 is replaced explicitly; its correlation logic is retained.

Original lines 305–317:

```text
00305 |         require(set(step)=={'request','observe'} and self.plan is not None
00306 |                 and self.plan['new_task']['kind']=='ordinary-document-task'
00307 |                 and isinstance(self.plan['new_task']['source_reference'],dict)
00308 |                 and self.plan['new_task']['request']==step['request'], 'exact_text_followup_plan_required')
00309 |         params={'chat_id':'PRIVATE_PEER_REDACTED','text':step['request']}
00310 |         metadata=run['request_metadata']
00311 |         require(type(params['chat_id'])is str and metadata.get('method')=='sendMessage'
00312 |                 and metadata.get('params')==params and metadata.get('body_sha256')==sha(enc(params))
00313 |                 and metadata.get('body_bytes')==len(enc(params))
00314 |                 and metadata.get('scenario_sha256')==run['scenario_sha256']
00315 |                 and user['timestamp']==run['sent_date'] and type(user.get('content'))is str
00316 |                 and user['content'].endswith(step['request'].rstrip('\n')),
00317 |                 'exact_native_text_sendMessage_correlation_required')
```
