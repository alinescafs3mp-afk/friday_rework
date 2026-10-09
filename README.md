# Friday_rework

Separate Hermes-based Friday implementation. Integration is under validation; no product acceptance or deployment is claimed.

Composition: pinned Hermes host, intact DeepSeek Harness coding worker, intact dedicated Agent Zero engineering worker, and verified Friday personality/Telegram deltas. Production inference uses explicitly configured existing local endpoints, with no automatic cloud fallback. Autonomous web retrieval, web access during both worker paths, and a working administrative WebUI are mandatory release capabilities; authorized web connectivity is separate from model routing.

The legacy Friday checkout, runtime, data and Telegram consumer stay preserved. Publication target: `alinescafs3mp-afk/friday_rework`, branch `main`. Secrets, private handoffs, donor checkouts, live runtime state and raw private evidence are excluded from source control. Sanitized, inert source snapshots and selected result extracts are published separately for analysis with their validation status.

See `docs/foundation-status.md` for verified progress and current gaps. See `sources.lock.json` for the selected upstream identities and `docs/integration-boundary.md` for the implementation boundary. The existing owner task register remains authoritative; this repository adds no dispatcher or second backlog.

See `docs/mandatory-web-admin.md` and `validation/acceptance-web-admin.json` for the owner's cumulative web/admin requirements and complete user journeys. These capabilities are not yet accepted.

[Donor capabilities and integration status](docs/donor-capabilities.md) distinguish planned, implemented, connected and verified functionality, including the mandatory web and administration journeys.

[Work log and intermediate analysis — 9 October](analysis/2026-10-09/incremental-01/README.md) record completed work, failed attempts, remaining gaps and next steps. This was the first partial publication; its observations remain historical.

[Expanded source, outcomes and process analysis](analysis/2026-10-09/incremental-02/README.md) adds 349 historical result summaries, 40 design/control plans, source snapshots and explicit remaining coverage gaps. It is an intermediate publication, not the completed daily checkpoint or a release.

[Additional outcomes and provenance](analysis/2026-10-09/incremental-03/README.md) closes the selected 171-row metadata omission table, including previously omitted failures, successful runs and exact Linux header provenance. These observations precede the reconciled daily cut.

[Recent fixes and integration decisions](analysis/2026-10-09/incremental-04/README.md) adds callback and TypeScript source repairs, independent findings and 36 selected process records. Runtime qualification remained pending at that cut.

[Cache identity, process ownership and review decisions](analysis/2026-10-09/incremental-05/README.md) adds later source corrections, their independent findings and the remaining execution gaps. This is the fifth intermediate publication. Installed journeys remain unaccepted.

[Daily work and coverage — 9 October](analysis/2026-10-09/daily/README.md) joins the five intermediate publications with the later Astra/Sol material, describes coverage boundaries and lists the next runtime acceptance work. Read its explicit cutoff and residual gaps; publication does not establish product readiness.

[Caller bootstrap failures and contract corrections](analysis/2026-10-09/incremental-06/README.md) adds the next completed source-analysis block after the verified daily commit `00c3b825260792b834e7f2aecf19eaabaa02935d`, including explicit late upstream-service carryover. F4/F5 remain unclosed; active successors and runtime acceptance are outside this cut.

Промежуточный [срез исходников F4 native/F5 bootstrap от 09.10.2026](analysis/2026-10-09/incremental-07/README.md) сохраняет полный изменённый код и три открытых source findings R1/R2/J1. Обе реализации не приняты; final build/F6 NOT_RUN, продуктовая приёмка не меняется.

09.10.2026: [incremental-08](analysis/2026-10-09/incremental-08/README.md) сохраняет объединённый исходник с независимо закрытыми J1/R1/R2 и первые две DSO-сборки PASS без загрузки. Полные изменённые тела и внутренние pin-map delta опубликованы для анализа; ABI/F6 и установленный продукт (7 journeys / 4 web) остаются UNACCEPTED.

[Первый primitive runtime: отказ и source repair](analysis/2026-10-09/incremental-09/README.md): фактический `EPROTO71` до target exec закрыт в исходные 180 с; восемь controls не приняты. Подтверждён uninitialized affinity tail, опубликованы пять полных исходников и реальная сборка исправленного C. Новая библиотека в срезе NOT_LOADED; sole cause и успешный runtime-повтор не доказаны. Full F6/GNU/all11/7 journeys/4 web UNACCEPTED.

10.10.2026: [последующий реальный запуск G2](analysis/2026-10-10/native-validation-g2.json) прошёл восемь native-проверок и независимое ревью точных результатов. Процессы завершены, блокировка освобождена. Это узкая приёмка native-проверок; полная приёмка Friday остаётся открытой.

[Первый GNU runtime](analysis/2026-10-10/gnu-runtime-first/README.md): исправлены и независимо проверены два несоответствия source bindings и caller lock; опубликованы восемь полных исходников. Реальная попытка завершилась с GNU exit125 до запуска target. Завершение процессов и освобождение блокировки подтверждены, попытка потреблена. Срез сохраняет отказ, ограничения CPU-наблюдений и следующий шаг диагностики; успешный GNU или продуктовый результат не заявлен.

10.10.2026: опубликованы [десять полных исходников и найденные причины отказов](analysis/2026-10-10/next-runtime-corrections/README.md). Последующий [исправленный GNU-запуск](analysis/2026-10-10/gnu-corrected-runtime.json) выполнил девять проверок и завершился с exit0; процессы закрыты, блокировка освобождена внутри исходного лимита. Независимая приёмка результата ещё идёт. Отдельный native fault repair собран, не загружен; полный продукт остаётся UNACCEPTED.
