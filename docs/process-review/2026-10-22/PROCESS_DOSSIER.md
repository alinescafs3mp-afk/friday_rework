# Friday_rework: фактическое досье процесса

Дата: **22 октября 2026 года, Europe/Moscow (UTC+03:00)**. Сбор начат в **22:01:04 МСК**. Основной воспроизводимый публичный срез — `main` **`64e74601d72b56fd92506e167462b19f068f8b4f`**; чтение дополнено уже существовавшими местными свидетельствами и указанными ниже сообщениями интегратора. Основной продуктовый срез — **22:11 МСК**, поздняя дельта интегратора — **22:18 МСК**; время завершения подготовки указано в конце. Новых продуктовых запусков ради этого досье не выполнялось.

**Вывод по имеющимся данным:** защитные проверки реально обнаруживали ошибки управления процессами, передачи полномочий и изменения чужого текста. Одновременно заметная часть возвратов происходит в подготовках: несовместимые схемы, неверные ожидания проверяющего, жёсткие ключи/числа и необходимость вручную привязывать один исправленный файл к нескольким потребителям. Универсальной оценки потерь в процентах нет. Последний проверенный установленный результат — Source110; последующий native entry завершился 0, а новая XLSX-отправка получила UNKNOWN_SEND без ACK и не принята. Принятый исходный код, физическая установка, READY, доставка и правильность ответа здесь разделены.

## А. Точка отсчёта и предел наблюдения

### А 1. Что проверено непосредственно

В начале чтения ветка — `main`, HEAD — указанный выше полный SHA. Единственное прежнее tracked-изменение — `docs/foundation-status.md`, принадлежащее владельцу; при подготовке досье оно не изменялось и не включалось в индекс. Невлитые кандидаты находятся также в отдельных защищённых рабочих каталогах. Публикация документов об этих кандидатах сама по себе не подключает их к обычному composer. Git читался с `GIT_OPTIONAL_LOCKS=0`.

Непосредственно прочитаны: полная директива на эту ревизию; опубликованные патчи и статусы, перечисленные в разделе З; адресные handoff/knowledge-map; выбранные поля фактической приёмки R45; текущие тексты местных native queue/Kimi/tester helpers. Исходные истории бесед, скрытые рассуждения, содержимое пользовательских документов и секреты не извлекались. Новых импортов продуктовых модулей, тестовых кампаний, HTTP/model/Telegram-запросов, установки или управления сервисом для отчёта не было.

Местные свидетельства обозначены устойчиво: `P` — checkout проекта; `H` — установленный private home Friday; `C/<assignment>` — защищённый cache пакета; `N` — native runtime helpers; `K` — каталог командного адаптера Kimi. `A-OLD/A-NEW`, `S-OLD/S-NEW`, `K-SESSION`, `BOOT-OLD/BOOT-CURRENT`, `BACKEND-OLD` заменяют реальные UUID, SID, boot/process/user/chat IDs и адреса. Эти обозначения сохраняют связи, но не являются исполнимыми путями. Реальные code-relative пути и безопасные инженерные параметры сохранены.

### А 2. Установленные байты и доступность — разные утверждения

Последнее непосредственно прочитанное `C/R45/ROOT-ACTUAL-INSTALLED-ACCEPTANCE.json`, SHA-256 **`29dcce9f67c91319e1a2a623285b5dd74e5407bdb413ec21f324beac2cfca16f`**, содержит следующий безопасный экстракт. Полный файл остаётся приватным, потому что содержит локальные пути и подробные инвентари; нижеследующий экстракт передаёт содержание вывода, а не только его хеш.

```json
{
  "state": "SOURCE110_INSTALLED_CURRENT_NONE_PRESERVED_NATIVE_START_NOT_RUN",
  "accepted": true,
  "actual_update_returncode": 0,
  "native_files_full_digest_matched": 17712,
  "source_layers": 110,
  "input_sha256": "de533c3916e05cee35796445c51c9aa51826c9c0a00ce33ee60efda7c2b7f0f0",
  "source_receipt_sha256": "3d68cf86785247dcfd24bdb361822b1e05758befcc4716f61b5cb1281a5fdfb2",
  "all4_physical_afterimages_modes_matched": true,
  "old_history_files_unchanged": 1096,
  "installed_history_files": 1109,
  "retained_data_files_unchanged": 566,
  "retained_directories_identity_mode_unchanged": 197,
  "profile_and_credential_bytes_unchanged": true,
  "unit180_unchanged": true,
  "native_start": "NOT_RUN",
  "newTelegram": "NOT_RUN",
  "full_release_accepted": false
}
```

Это Root-проверка физической установки, не повторённая независимым аудитором на `H`. Проектный вход имеет 293 файла. Composer-идентичность: Hermes donor commit **`781334eea4b9225a3e194faf0c241d9afe218634`**, tree **`7d90fdf1fc75a1cd5277a6ccf514e0e2b642136e`** → неизменённый 109-слойный предшественник с receipt **`b2cdf42430e38721095decc95448375af33ee011fa09faaead954acdc71905ef`** → слой `accepted-own-copy-xlsx-cell-edit-source110` с manifest SHA **`f46cbbd421f55bf090958be9af87600656646efea3ffb3201c1a174e3822744e`**, patch SHA **`d4292c495f208134313261f395480fafa4a276861148a40634b2bf4b245af88f`** → конечный receipt `3d68cf…` выше. [Публичный manifest110][p-xlsx-manifest] даёт весь набор prerequisite patch pins, точные before/after четырёх файлов и режимы. Название Source110 без этих pins недостаточно. Полный 17 712-файловый итоговый receipt публично не размещён; реконструкцию всей установки только из этого досье не обещаем.

Проверка выполнена примерно в **21:59 МСК**, её собственное измерение — **3,264 с**. На момент этой установленной проверки gateway **STOPPED**, workers **OFF**; native start и Telegram/XLSX **NOT_RUN** именно по этому свидетельству. Прежние READY и успешные web/PDF/DOCX относятся к предыдущим операциям. После потери питания нельзя считать их нынешней доступностью. [Публичный postpower-срез][p-power] отдельно фиксировал восстановление локального inference; готовность metadata endpoint не равна выполненному inference. Новое наблюдение всей инфраструктуры ради досье не проводилось.

**Поздняя дельта, 22:11 МСК:** непосредственно прочитан `C/R45/ACTUAL-NONE-NATIVE/TERMINAL.json`, SHA **`b8683c0360de500c1949381aef9ef0a3cd8719a3597a5f47f95f2fe13167b704`**: `state=SUPPORTED_NATIVE_SUCCESS_INSPECTOR_NOT_RUN`, native returncode0, `ORDINARY_NATIVE_GATEWAY_OBSERVED`, workers=false, inspector/stop=NOT_RUN, original reserve preserved. Native dispatch→terminal **80,3865 s** — длительность native entry, **не** отдельно измеренное время рождения service→READY. В handoff `ready:false`, `runtime_acceptance=PENDING_GENUINE_INPUT`: наблюдение/передача native gateway ещё не пользовательская приёмка. Gateway в этой поздней точке живёт под exact Root-owned invocation; stop 70 остаётся обязанностью уже выполняемой операции. По сообщению Root новая XLSX-отправка 22:07:52 получила UNKNOWN_SEND: одна попытка, ACK отсутствует, автоматического resend нет, доставка не установлена. Подробнее Д 5. Это позднее состояние выше раннего STOPPED; новый XLSX PASS не объявлен.

### А 3. Кто выполняет работу

| Обозначение | Фактическая роль и граница |
|---|---|
| Astra / Root | Один лид и единственный интегратор. `Root` в отчётах — не ещё один независимый инженер. В текущем установленном пути та же Astra является оператором установки и tester/получателем Jarvis. Поэтому два её отчёта не являются двумя независимыми live-проверками. |
| Sol | Отдельный самостоятельный инженер в своей существующей видимой native TUI; реализация, подготовка композиции и независимое ревью по конкретному TASK. Общего Sol goal нет. |
| Kimi | Отдельный инженер пользовательских сценариев через действующий ACP-сеанс `K-SESSION`; не production backend Friday. Облачная разработка не заменяет локальный inference продукта. |
| reviewer | Роль конкретного задания: чтение diff/контрактов, изолированные проверки либо проверка сохранённых фактов. Внутренний Codex child может исполнять эту роль; он не новая корневая Astra/Sol. |
| operator / tester | Полномочия на конкретные эффекты и единственного receiver. Наличие роли в тексте не выдаёт доступ к `H`, секретам или новому запуску. |
| Grok | Историческая/доступная лабораторная роль. В разобранном текущем пути её нового RUN не обнаружено; не приписываем ей работы Kimi. |

Модель не выводилась из имени или автора коммита. Проверенная запись восстановления `A-NEW` указывает **gpt-6.1-sol / ultra**; handoff сообщает те же фактические параметры Sol. Fast-настройки сохраняются, но per-request tier из turn metadata не установлен. Kimi binding/handoff указывает `kimi-code/k3-256k`, `max`, `auto`; это сведения о настроенном инженерном клиенте, не измерение биллинга.

Активный связанный путь: Astra завершила native entry установленного 110 и разбирает UNKNOWN_SEND новой XLSX-задачи; Sol S159 готовит source-only переход retained inactive A0 registration/ordinary ancestry; Kimi B54 — source-only исправление происхождения даты, независимо отвергнуто по новому дефекту. Worker/date/full-release работы выполняются параллельно и **не являются условием обычного XLSX**. B54 не принят и не установлен. Необходимые full 170/120/catalog 840, workers, DSH/A0, administration, memory/skills и полный форматный набор остаются открытыми.

### А 4. Как попадают правила в новую сессию

В точке `P` и проверенных родительских каталогах файла `AGENTS.md` **нет**. Рабочие AGENTS-инструкции присутствуют как предоставленный владельцем текст текущей сессии; это нельзя выдавать за автоматически загружаемый файл checkout. Адресный handoff содержит `SESSION_HANDOFF.md`, малый `CURRENT_STATE.json`, `RESTORE_NATIVE.md`, `GOAL_SCOPE.txt`, `KNOWLEDGE_MAP.private.json`; owner paste требует проверить SHA и прочесть первые три, затем остальные адресно. Действующее сообщение после `/new` требует адресно прочитать свежий handoff/малый state по проверенным SHA, затем процедуру восстановления и необходимые ссылки knowledge map; полные архивы не подгружаются. Старые исходники, результаты и сессии сохраняются, скрытая память не считается автоматически перенесённой. Это безопасное описание операционного правила; приватный handoff дословно не публикуется.

Наблюдаемое выполнение: `N/astra-new/ROUTE-VERIFIED.json` и `ROUTE-RESTORED.json` установили единственные TUI/backend/writer и `LINK_READY` нового собственного маршрута **20:28:15 МСК**, сохранив уже новый маршрут Sol; `ACTIVE-GOAL.json` — новую активную цель **20:30:24 МСК**. Owner-контрольная точка «20:30» поэтому согласуется с артефактами, но не является точным временем обоих `/new`. Старый goal остался paused; его **184 471 872 tokens / 391 660 s** — исторические native-счётчики одного сегмента, не стоимость этой ревизии и не сумма проекта. Новые счётчики при создании были нулевыми; вручную их не переносили. Факт восстановления и последующая R45-работа подтверждены; прочтение агентом каждой строки всех архивов не наблюдалось и не требуется.

## Б. Сквозная карта процессов

Основной путь: **потребность → конечное назначение → код и короткие проверки → независимое ревью затронутого → композиция exact bytes → свежая привязка состояния/допуск → одна установка → проверка установленного → настоящий READY/generation → Telegram-задача → артефакт/семантика/сохранение → отдельное продолжение → следующий пакет**. Публикация существенных блоков идёт параллельно; полного релиза ради неё не ждут.

| Переход/семейство | Инициатор, вход → выход, потребитель | Реальный барьер/возврат и выход из петли |
|---|---|---|
| Выбор следующей задачи | Astra выбирает текущий пользовательский отказ или готовый независимый пакет; TASK задаёт область записи, ресурс, исходный снимок, допустимые эффекты, бюджет и DONE WHEN. | Неверная предпосылка приводит к сохранённому отказу и изменению гипотезы/контракта. Новое безопасное чтение не требует повторного разрешения владельца. Полный backlog не становится условием каждого обычного сценария. |
| Sol TASK → RESULT | Exact immutable ref/SHA, assignment/generation → native queue существующей `S-NEW`; Sol читает точные входы; RESULT принимает Astra. | Перед новым независимым TASK — один завершённый native compact на idle-границе; continuation того же назначения без второго compact. ENQUEUED подтверждает очередь, не исполнение. Результат проверяется по ref/hash, затем удаляется только его exact item. |
| Kimi TASK → RESULT | Astra authorizes текущий assignment с CAS/epoch/session; один ACP prompt; результат+checkpoint+terminal turn → Astra receipt. | Следующее самостоятельное назначение после завершения turn/effects и native compact той же сессии. Rejected result тоже может корректно закрыть задачу. Неразрешённая/неопределённая отправка не повторяется вслепую. |
| Native children | Родитель выдаёт конечный ограниченный пакет штатным collaboration API; результаты и own cleanup возвращаются родителю. | Исторические `lifecycle.py prepare-spawn/prepare-followup/complete`, watcher и реестры Astra/Sol отменены. Их не вызывали для досье; родитель отвечает за качество/завершение собственных процессов. Текст `LIFECYCLE` в TASK сам по себе не действующий hook. |
| Реализация и snapshots | Sol/Kimi/child пишет в своей выделенной области; Astra интегрирует. Diff, manifest, tests/evidence → независимый reviewer. | Замороженные bytes/pins нельзя подменять очередной mutable редакцией. Новая дельта получает новую точную идентичность; неизменные проверки переиспользуются с указанными предпосылками. Старое одобрение не переносится на иной candidate по Source-номеру. |
| Ревью и компоненты | Автор коротко проверяет реальный изолированный путь и значимые negatives; reviewer читает связный пакет и проверяет рискованные seams. | Реальный HIGH/MEDIUM возвращает исправление в затронутую область. AST/fixtures доказывают wiring/условия, но не installed authority/live. Cached semantic review полезно, однако не второй live receiver. |
| Composer/build | `scripts/hermes_prepare.py`: pinned donor + manifest DAG → source receipt с layers/files; PM/build/frontend — отдельные подтверждения. | `source_identity`, `overlay_layers`, `_compose` проверяют donor/index, prerequisite SHA, exact inventory, до/после/bytes/modes. Для неизменного composed tree новая сборка ради очередной копии не нужна. |
| Producer → consumer | Привязка готовит schema/request/core, source/data inventory, current configuration, operation/clock, seals; consumer повторно проверяет точные входы. | Изменение схемы/поля/нового файла требует согласовать обе стороны. Отказ до эффекта не продуктовый runtime FAIL. В Source95 consumer ожидал отсутствующий `frozen.input`; исправлен реальный schema join, не подставлено фиктивное поле. |
| Maintenance/install | Astra — единственный оператор. Свежие stopped/identity/source/data/lock/CAS + beforeimages → одна durable intent/транзакция → физическая проверка. | Нельзя писать поверх чужой версии, трогать unknown owner или повторять consumed effect. Ошибка ведёт к owned rollback и проверке его фактического результата; исправленный преемник — отдельная легитимная операция с сохранением прежнего FAIL. |
| Native start | Exact installed input + выбранный PM Python + source guards + native unit/local credentials → единственный user-systemd start → notify READY и generation proof. | Unit/process/incarnation/owner mismatch или нехватка оставшегося бюджета запрещают start. Обычный `start-telegram` отделён от full start, который проверяет обоих workers/UI. READY не отменяет generation/custody. |
| Telegram capture | Один receiver Jarvis; precommitted scenario/fixture/run ID, один send/ACK, raw updates до cursor commit, fixed receive window, terminal drain → сохранённое evidence. | Нет blind resend после UNKNOWN; окно не продлевают задним числом. `advance` существует для иных legacy intermediate steps, но для final bounded reply **кодом запрещён**. |
| Семантика/пользователь | Root сопоставляет фактический запрос, delivery, сохранённый ответ, физический документ и private oracle; отдельный reviewer проверяет доступную фактуру. | Ошибочное ожидание тестера исправляют по исходному контракту, оставляя первоначальную ошибку. Правильный ответ не объявляется FAIL из-за ненужного слова или ID иного namespace. Full-window и semantic pass остаются разными выводами. |
| Продолжение/recovery | Отдельный естественный follow-up, проверка persisted own-session state; после outage — текущая готовность/эффекты/курсор, native восстановление существующей TUI. | Ни питание, ни model capacity не оправдывают дубликат старого TASK/request. Один штатный continuation незавершённого задания допустим после проверки факта остановки; повторный отказ — реальный blocker, независимая работа продолжается. |
| Publication | Astra публикует код и обезличенные результаты существенными блоками прямо в существующий main; сохраняет source/install/live distinctions. | Нет daily21–22 schedule, нового согласования всех троих или требования full release до публикации. Проверяются exact exported hashes/patch paths/privacy; продуктовые tests не повторяют только ради отчёта. Неразобранные private raw dumps не экспортируются. |

Выход из ревью-петли — устранённый конкретный дефект и проверенная изменённая область, а не заданное число кругов. Выход из installation-петли — принятая физическая идентичность или честный rollback/STOP_UNCONFIRMED. Выход из capture — terminal evidence/неопределённость в прежнем окне, а не обещание будущего PASS. Дополнительные отчёты, не потреблённые для следующего решения, не объявляются полезной проверкой: полная инвентаризация таких сиротских отчётов не выполнялась.

## В. Требования, полномочия и обязательные барьеры

### В 1. Происхождение и актуальность правил

| Правило | Источник/дата → где читается | Код/фактическое соблюдение или конфликт | Кто меняет |
|---|---|---|---|
| Пользовательская функция, разумный debt, автономные обратимые шаги | Owner corrections, адресный handoff22.10 и настоящая директива §§2,4; owner paste после `/new`. | R45 продолжается без нового разрешения на каждый bind; worker/date параллельны. Это инженерные полномочия, не разрешение менять inference/server/credentials. | Owner задаёт границы; Astra выбирает безопасные шаги внутри них. |
| Холодный gateway180 как штатное конечное окно | Owner22.10; [startup policy][p-startup]. | Effective unit180; исторический env-key содержит `TEST`, отсутствующее значение всё ещё даёт 90, outer wrapper удаляет ambient key. Поэтому требуется exact180 на последнем native entry. Это известный debt, а не отмена решения владельца. | Astra может исправлять поддержанный путь в полномочиях; модель/сервер отдельно у владельца. |
| Модели, Fast, endpoints не тюнинговать самовольно | Owner10.10, последующие corrections17/22.10; текущие session instructions/handoff. | Native `A-NEW`:6.1-sol/ultra; сохранён Sol route/config. `GOAL_SCOPE` и старый objective всё ещё содержат gpt-6-astra/FastOFF — **устаревшая подпись**, не текущий приказ. `compression.none` отдельна от основной модели; отключённый владельцем offload самовольно не возвращается. | Owner. |
| Local-only production, данные/доступ/секреты/процессы | Полная owner V2 scope, Kimi team directive20.10, ревизия 22.10. | Native credential/route/user isolation, pin/owned-file/CAS, stop/cancel; cloud Kimi только инженер. Старые Friday OFF, Pandora исключена. | Owner меняет область; инженер исправляет реализацию без ослабления гарантии. |
| Один интегратор; независимые инженеры | Owner, Kimi directive20.10 §2. | Astra устанавливает/публикует; Sol/Kimi отдельные конечные пакеты. Внутренний reviewer не второй интегратор. | Owner роли; Astra task write scope. |
| Отмена Astra/Sol контролирующего обвеса | Прямое owner14.10 в текущем AGENTS-тексте, повторено handoff. | `sol-link-native-send.py` прямо содержит `# Owner removed custom lifecycle authority; native queue and event receipts remain.` Старые функции `_lifecycle_run` ещё в файле, основной dispatch их не вызывает. Наличие мёртвого кода не доказательство действующего hook. | Owner; не восстанавливать по архиву. |
| Один pre-task compact Sol | Отдельное owner16.10 исключение, current AGENTS; после него TASK exact refs. | S157: premature unstarted TASK был exact deferred, completed compact проверен, payload restored once; continuation S158 без нового compact. Правило автоматически не распространяется на собственных children. | Owner; Astra инициирует только между заданиями. |
| Kimi native compact/lifecycle | Самостоятельная owner directive20.10 §§1,5,8; local `friday_kimi_peer.py`. | Same session, genuine turn end/idle/receipt/context checkpoint. Узкое требование только accepted_result исправлено на accepted **или closed rejected**; остальные гарантии сохранены. Это Kimi adapter, не возвращённые Astra/Sol lifecycle hooks. | Astra исправляет адаптер в выданной области; owner меняет жизненный цикл. |
| Не повторять эффект/не сбрасывать часы | Owner и реальные installer/tester contracts. | durable ID+UNKNOWN reservation, consumed journals, inherited monotonic deadlines; новый разрешённый start установленного артефакта отделён от replay R39/R44. | Инженер может организовать отдельную корректную операцию; не переименовать старую ради обхода consumed. |
| Fresh mutable-state checks / reuse unchanged source | Owner11/14.09 и текущий handoff; installer/CAS. | S158 проверяет новую operation, затем final bound tuple, не повторяет весь S157. Worker source переиспользует 52+25 unchanged controls. Новое состояние `H` нужно проверять заново, даже если source неизменен. | Astra/reviewer по конкретным предпосылкам; не TTL доверия. |
| Публикации в main без daily schedule | Owner14.10 заменяет 09.10, current AGENTS. | Обезличенные source-only блоки публикуются до full acceptance. Dirty owner document сохранён. | Owner политика; Astra состав checkpoint. |
| Сессии 20:30 | Прямое owner22.10, after-new paste. | LINK_READY20:28 и active goal20:30, preserved route Sol; последующий actual R45. Не доказана мистическая полная передача памяти; адресные checkpoints сохранены. | Owner инициировал `/new`; восстановление выполняет Astra. |
| «Вторая смена», улучшенные уведомления, reviewer-fix | По директиве ревизии 4.9–4.10 отложены/кандидат. | Нового поручения об их включении в прочитанных материалах нет. Досье не вводит их в эксплуатацию. | Owner для нового scope; локальный write scope может разрешать reviewer fix отдельно. |

Происхождение каждого исторического числа в тысячах старых asserts не восстановлено. В таблице ниже кодовые ограничители называются **ограничителями реализации**; без owner-источника они не переименованы в неизменяемые требования безопасности. Ссылка на прежнего внешнего аудитора не делает правило непересматриваемым.

### В 2. Каталог барьеров: что именно закрывается

| Класс и точное место | Что запрещает/риск; пример | Актуальность и частота | Цена и допустимое упрощение |
|---|---|---|---|
| Native single writer/session: `N/sol-link-native-control.py::NativeControl.__init__,call` | Любое peer RPC при неединственном designated TUI/backend, foreign writer или неправильном thread/home. Предотвращает чужое управление; не запрещает offline код. | В начале соединения, exact thread на каждый RPC; изменение endpoint/writer/session инвалидирует. | Model-free bounded RPC, open5/close2/read10 s; фактическая суммарная цена не измерена. Нельзя заменить наличием socket; текущий helper можно переиспользовать. |
| Queue event/custody: `send::reserve,_queue_rpc`, `native_queue::consume,start,defer,restore` | Дубликат TASK, удаление неподтверждённого ref, автозапуск хвоста очереди. UNKNOWN записывается до queue/add; exact item удаляется после evidence. | Один reservation/event; фактическое чтение очереди на содержательном checkpoint; no repeated model polling. | Есть реальные дополнительные defer/restore при S157. Не нужен ACK-only круг, массовое delete запрещено. Exact hash join и once-only сохраняются. |
| Kimi authorize/compact: `command_authorize_task`, `derive_task_lifecycle`, `command_compact_request`, `validate_compact_outcome` | Новый TASK/compact при active/unknown turn, чужом session/epoch, незакрытом результате. Закрытый rejected не должен держать исправление в тупике. | CAS assignment; before/after cursor, exact request/session, idle, receipt, result_ready и native completion; новое assignment/turn меняет предпосылки. | Локальный protocol/receipt overhead есть, точного разложения нет. Исправление accepted-only уменьшило барьер без признания плохого кода хорошим. |
| Source integrity/composition: [hermes_prepare][p-composer] `source_identity,overlay_layers,_compose`; [install][p-install] `source_checked,composition_checked` | Подмена donor, утрата layer, неверные bytes/modes, import чужого validator; закрывает composition/install/start. | Неизменные bytes и exact dependencies; source receipt не live-допуск. Полная проверка composer и фактического установленного — разные объекты; повтор того же frozen source без причины избыточен. | Один полный guard scan Source90:4,271 wall/4,251 CPU с,233 320 205B,17 710source; **не** измерение общего количества startup scans. Source99 composer15,4385 с. Reuse допустим при прежних точных предпосылках, не по времени жизни кеша. |
| Schema/pins/counts: [ordinary installer][p-ordinary] `update_inputs,bundle_manifests_checked,project_update_inputs`, [Source95 delta][p-schema] | Необъявленная дельта, неверный prefix/history/input. Были ложные отказы на несуществующий `frozen.input` и new-file mode. | Producer/consumer должны согласовать schema, count, hash и состав новых файлов; bound tuple проверяется после материализации. | Новые версии/два связывания стоят передачи и проверок, точное время не отделено. Проверять на реальном consumer до дорогого gate; считать инвентарь из заявленной дельты при сохранении exact set/hash. |
| Mutable-state/auth/data/CAS: installer `owned_file,pin,stopped_consumers,update,restore_update_files`; внешние corrective функции | Запись поверх чужого файла, живого consumer, drift данных/credentials, без rollback. R44 rollback действительно проверял 17 711 native, не просто rc0. | Свежие stopped/locks/current snapshots нужны непосредственно перед эффектом и при CAS; старый source review не заменяет их. | Инвентаризация защищённых данных отдельно от логов/pycache/PID-lock transitions. Разрешённые изменения должны быть перечислены; общее «FS неизменна» неверно. Root принимает точную ограниченную операцию. |
| Service READY/generation/custody: [startup patches][p-startup], `gateway_preflight,gateway_observation,ordinary_start`; containment Budget | Запуск чужого unit, clipped command без stop reserve, ложный READY по одному PID или историческому статусу. Первый 180 READY прошёл, generation отказал — Telegram не отправляли. | Unit/process incarnation, source/current pins и boot; полная 60 s proof ограничена inherited deadline. | Реальные холодные READY около 92–94 с; proof/identify отдельны. Нельзя убрать настоящий notify или owner stop. Рабочий 180 не требует полного DSH/A0 gate обычному chat. |
| Tester custody/semantic boundary: `Runner.verify_window,ready,advance`; [tester patch][p-tester-patch] | Подмена oracle, resend UNKNOWN, ретроспективное расширение окна, выдача captured за semantic PASS. | Immutable scenario/send-window, same sender/chat/reply-to и отдельные namespace; terminal empty drain в фиксированном окне. | Capture90 может переждать ответ 28 с; новый заранее объявленный 180 нужен для прежнего 117 s ответа. Это цена покрытия окна, не latency модели. Ошибочные literals/ID проверяющего можно исправлять по контракту без повторной отправки. |
| Full release | Только заявление о полном релизе:170/120/catalog 840, workers/DSH/A0/admin/полная matrix/live. | Финальный проверяемый артефакт и полный обязательный scope; локальный PASS его не заменяет. | Не блокирует независимый ordinary chat/file или source publication. Изъятие scope требует owner, подбор затронутых коротких проверок — инженерное решение. |

Сохранность данных здесь не означает полного равенства файловой системы. R32 отдельно разрешал 8 config/seal изменений и учитывал 9 native PID-lock metadata transitions, сверяя остальные защищённые файлы. Source90 diagnostic выполнял WAL-aware read-only/query-only SQLite quick checks; SQLite создала zero-byte WAL/shared-memory sidecars, поэтому там прямо не заявлены whole-database byte equality или нулевые FS-эффекты. [Свидетельство][p-diagnostic]. Аналогично pycache/log/own journal нельзя молча причислять к пользовательским данным или разрешать менять без указания области: актуальный consumer должен перечислять допустимые дельты и защищаемый состав.

Известные статусы имеют следующие операционные значения:

| Статус | Что уже можно/чего ещё нельзя утверждать |
|---|---|
| `PASS` / `PASS_SCOPED` | Только названный проверенный контракт/случай и его версия. Нет наследования на все форматы, runtime или release. |
| `SOURCE_ONLY` | Можно рассматривать/компоновать проверенные bytes; установки, native authority, worker admission и live нет. |
| `EVIDENCE_READY` + `RECEIVED_UNGRADED` + `NOT_ESTABLISHED` | Закончен сбор ограниченного evidence; независимая семантическая оценка делается снаружи. Для **bounded_reply_capture нет перехода к финальному tester PASS**, даже при правильном файле. |
| `NOT_RUN` | Действие не выполнено; не скрытый FAIL и не обещанный PASS. Зависимый сценарий остаётся таковым с причиной. |
| `STOPPED` / `runtime_ready=false` | Capture/service/operation остановлены согласно своей области; это не всегда отсутствие уже доставленного ответа. Текущая доступность не доказана. |
| `UNKNOWN` / `STOP_UNCONFIRMED` | Неизвестный эффект/неподтверждённое прекращение. Нужна адресная сверка, не blind retry и не заявление о безопасном завершении. |

### В 3. Минимальная проверяемая местная логика

Локальные helpers не представлены как доступные GitHub-файлы. Здесь приведены небольшие подлинные фрагменты; пропуски обозначены `…`, приватные значения путей/ID опущены, условия не улучшались при публикации. Полные SHA текущих прочитанных файлов: `sol-link-native-control.py` **`7b616fe144e0641dc402f2051ef0226ff59fe132c36885474939623ba428da68`**; `sol-link-native-send.py` **`650fc9d86ceafce1b0767e8076373f41a67e37a6da9a32580b58c5203e5b48c6`**; `native_queue.py` **`20236c3266ab104ddc0e6a3d0d8b97023277bd6f352360e4f167fe878abc3d5d`**; `friday_kimi_peer.py` **`45ea00fe70f18cad2a266e83ae59403da2082579cd47ca7ac5ca57382c30f1b8`**.

Native owner gate и фактическая отмена lifecycle authority:

```python
if (len(live['active_tui_pids']) != 1 or len(live['backend_pids']) != 1
        or live['foreign_writer_pids']
        or not set(live['backend_pids']).intersection(live['active_writer_pids'])):
    raise RuntimeError('Expected exactly one designated TUI and loaded backend')
# sol-link-native-send.py, основной dispatch:
# Owner removed custom lifecycle authority; native queue and event receipts remain.
result = _queue_rpc(peer, args.event, message, forensic_path, evidence)
```

Once-only и exact consumption, `reserve` / `native_queue.consume,start`:

```python
fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
# FileExistsError: сверяются event/hash/recipient/generation/assignment; resend нет.
…
if digest(ref) != notice["sha"]:
    raise RuntimeError("queued peer artifact hash no longer matches")
if notice["ref"] not in known or notice["sha"] not in known:
    raise RuntimeError("evidence does not bind both queued ref and SHA-256")
…
await control.call("thread/queue/delete",
    {"threadId": control.thread, "queuedSubmissionId": args.queued_id})
…
if [row.get("id") for row in rows] != [args.queued_id]:
    raise RuntimeError("start refused: native queue must contain exactly the requested item")
```

Kimi закрытый rejected result и настоящий compact — [публичный точный diff][p-kimi-patch], current `command_compact_request` / `validate_compact_outcome`:

```python
require(lifecycle["terminal_reason"] in {"accepted_result", "rejected_result"}
        and not lifecycle["evidence_warnings"], "compact_task_not_accepted")
checkpoint = lifecycle["checkpoint"]
require(checkpoint is not None and checkpoint["state"] == "result_ready",
        "compact_checkpoint_not_ready")
result_receipt_states = {"rejected"} if lifecycle["terminal_reason"] == "rejected_result" else ACCEPTING_RESULT_STATES
…
compact_idle(proof)
compact_rpc_response(proof.get("native_response"), original["native_request"]["id"])
require(proof.get("recognized_native_command") == "compact", "compact_not_recognized_native")
…
require(native.get("outcome") == status and native.get("error") is None,
        "compact_native_not_successful")
# COMPACT_CONFIRMED:
require(native["cursor_after"] > native["cursor_before"], "compact_native_observation_not_new")
require(native.get("context_checkpoint_observed") is True, "compact_context_checkpoint_missing")
```

Tester SHA **`04b38ebc05a89871a9593c32aa5c46914020ec4348909ca06571dce35bf67291`**, `Runner.advance` — существование метода не означает его доступность bounded capture:

```python
if (type(run.get('step')) is not int
        or not 0 <= run['step'] < len(run['scenario']['steps'])
        or run['step'] + 1 >= len(run['scenario']['steps'])
        or reply_capture(run['scenario']['steps'][run['step']]['observe'])):
    raise Refused('A final or bounded reply capture step never advances; evidence is terminal')
```

## Г. Действующие числа и вложенные бюджеты

Значения относятся к указанному entry/операции, а не ко всем возможным путям Hermes. `wall s`, `CPU s`, байты, символы и токены не складываются между собой.

| Ограничение | Effective value / старт / область | Источник, исчерпание и изменение |
|---|---|---|
| Service cold start | **180 wall s** от native service start; Type=notify | Owner22.10 и [policy][p-startup-status]; timeout → FAILED/owned stop. Exact180 final env обязателен; global absent default90 исторически сохранён. |
| Command / proof / identify | **210 / 60 / 20 wall s** для explicit180; default identify5 | `ordinary_start`, `gateway_observation`; proof начинается после command и capped inherited deadline. Не дополнительный новый внешний бюджет. |
| Stop/watchdog | **70 wall s stop**, **30 s runtime watchdog** | Тот же unit/policy; stop reserve выделен заранее, NRestarts проверяют. Не заменять stop таймером observer. |
| R45 enclosing operation | **3600 wall s**, reserve **180 s**, origin+absolute monotonic deadline | Один original clock; installation, verification и дальнейшая native подготовка расходуют тот же остаток. Не reset после исправленного bind. |
| Native preparer planning allowance | preflight **90**, command 210+proof 60+containment1, stop 70+reap0,25+transition0,25+accounting1,5 | `prepare_native180_R45…py`; 90 — явное допущение, не физическая гарантия. Late admission остаётся решающим. Root floor =180+90+271+72=**613 s**. |
| Generic install Budget | `30..7200s`; отдельные update request обычно `30..180s` | [runtime_containment::Budget][p-budget], ordinary schema. `deadline <= start+seconds`, check before/after call, exhausted → refusal. Схема consumer может быть уже общего Budget. |
| Source composer | default **120 s**, allowed `(0,1800]`; monotonic от preparation | [hermes_prepare::preparation_budget][p-composer]. Partial destination сохраняется; не подменяет deployment budget. |
| Sol S157/S158 | **1800 s / reserve 120 s** каждый independent assignment | Original task clocks. S158 Part1→Part2 continuation сохраняет один clock/compact; core и final binding проверяются отдельно по изменившимся входам. |
| Выбранные source-review ресурсы | **2 CPU / 3 GiB AS / 512 MiB file** по TASK; отдельные старые harness2 CPU/1 GiB/CPU240/file64 MiB | Это ограничения конкретных изолированных проверок. Нативный gateway путь сохраняет **24 CPU affinity и unlimited AS**; не переносить в него child limits. Нового performance measurement нет. |
| R32 settings CPU | Первоначально **55 CPU s**, continuation **240 CPU s**; прежний wall clock/reserve | Первое действие остановилось после 2 из 8 settings/seals; новая CPU allowance не переоткрыла consumed transaction и не обнулила wall. |
| Tester scenario | **10..1800 wall s**; up to8steps/200updates, pacing1..60 s | `validate_scenario`; run deadline от создания run. Новая scenario нужна до send; внутри старой нельзя расширять окно. |
| Capture / ACK / cleanup | bounded window **1..600 s**; обычные реальные случаи 90; новый XLSX planned180/deadline 300; ACK **10 s**, cleanup **5 s** | `validate_reply_capture`, `Runner.send` admission повторяется после preflight и прямо перед send. Terminal drain входит в прежнюю цепь. |
| Tester HTTP/inputs | Один HTTP capped `min(10, remaining)`; whole deadline включая DNS/TLS/body; outgoing **1 MiB**, received **8 MiB**, response text8000chars/max64 messages/max1document | Canonical tester/manifest. Caption1024Unicode и 1024UTF16/4096UTF8bytes; no redirects/private upload source. Exhaustion/UNKNOWN не дают resend. |
| Web extraction | Existing **30 s /1MB** transport;50000 requested provider chars;15000 inline/private paging | [Exa patch/status][p-status]. Размер текста не доказательство полноты произвольной страницы; capped request дешевле переписывания транспорта. |
| Protected auxiliary compression | context **40960 tokens**, safety≥**1024**, output **8192**, input allowance **31744**; schema≤**2048 chars**, escaped≤**12288B**; `reasoning_effort:none` | [policy/source 105][p-none], [patch][p-8192]. Total includes actual rendered template/tools/input+reserve+safety. Visible chars не hidden reasoning tokens. Основной context 262144 этим не уменьшается; серверное окно не меняли. |

Фактическая вложенность R45 (расходуются остатки одного clock):

```text
original Root wall deadline = origin + 3600
└─ workcut = Root deadline − 180 (сохранённый внешний reserve)
   ├─ уже прошедшие bind/review/install/verification уменьшают остаток
   ├─ перед preparer нужен остаток preflight90 + native271 + tail72
   ├─ native deadline = workcut − stop70 − reap0.25 − transition0.25 − accounting1.5
   │  ├─ imports/preflight/source/credential/unit checks
   │  ├─ late floor: remaining ≥ command210 + proof60 + containment1
   │  ├─ systemctl start: весь210, не clipped остаток
   │  └─ proof deadline = min(inherited native deadline, proof_start + 60)
   │     identify timeout = min(20, proof remaining)
   └─ owned stop/cleanup в сохранённом tail; Root reserve180 не расходуется работой
```

Подлинный cached installed caller `ordinary_start` (SHA start-file **`129d25551be12742d11445d9f2c70fb1e6420d3132f7785e2d1a621761ea3657`**, изменение доступно в [generation-handoff.patch][p-generation]):

```python
budget.check(reserve=command_wait_seconds + 60 + 1)
custody.run(command, source, timeout=command_wait_seconds,
            require_full_timeout=True, timeout_reserve=60)
proof_started = time.monotonic()
proof_budget = Budget(60, started=proof_started,
    deadline=min(budget.deadline, proof_started + 60))
gateway_observation(home, proof_budget, identify_timeout=20.0)
```

Здесь `command` сокращает только длинный argv systemctl, не меняет условие. В Root caller `until` использует `min(deadline, ROOT_DEADLINE)-monotonic-reserve`; создание нового 60 s proof не продлевает inherited deadline. R39 доказал реальную проблему: подготовка оставила около 242 s при late floor271. Установка уже прошла; service ещё не запускался. Новая конечная операция 1800 s на **том же артефакте без переустановки** затем открыла настоящий start. Это самостоятельное разрешённое действие после закрытого R39, не продолжение его истёкших часов.

Для Telegram admission: до send должно оставаться **ACK10 + полное capture window + cleanup5**; окно привязывается к actual confirmed-send boundary, затем неизменно. Быстрый ответ 28 s не сокращает заранее выбранные 90 s покрытия. Исторический компакт 306,624 s не делает его старое 90 s окно полным.

Точность размеров: Source104 `prompt_tokens=6350` — сохранённое фактическое usage, Source105 `6792` — rough estimate, не provider usage; synthetic post-reboot `5712` prompt/76completion — отдельный вызов, не оценка всего 18-call compact. Hidden reasoning usage неизвестен. Строки, UTF-8/escaped bytes, actual tokenizer counts, tools/template и output reserve отдельно проверяются; окно сервера по этим наблюдениям не меняется.

## Д. Восемь реальных последовательностей и стоимость

Числа ниже — локальные наблюдения выбранных случаев, не общая статистика проекта. Календарное ожидание, CPU, latency и стоимость участников не суммируются. Там, где нет полной хронологии author time/queue wait, записан пробел.

### Д 1. 90 → 180, затем отдельный generation handoff

**Действие → участник → результат.** Source95/96 реально исчерпали 90 s, owned cleanup подтверждён. Source96 sampled await указывал на secondary-profile onboarding;14 наблюдённых guard spans суммарно 36,468 s, но caller и полнота учёта неизвестны. Это не доказанная единственная причина timeout. Owner разрешил/затем принял 180 штатно → команда собрала узкую policy → install43,507 s → independent installed check38,795 s → READY92,134598 s → **generation FAIL3**, никакого Telegram send. Тот исторический эксперимент точно восстановил 90 (35,161 s). Поздний owner standard180 отменил дальнейший auto-restore90.

Sol S120 подготовил узкую handoff-правку identify5→20 внутри proof 60 при тех же восьми generation comparisons → project-only install64,047 s без замены native/plugins → новый supported start READY92,917672 s/generationPASS → genuine first reply33,690 s, contextual follow-up4,069 s. Независимый S123 принял scoped smoke. Warm reply5,026 s сохранился, но observer STOPPED/poll_http UNKNOWN90 остался негодным для full-window proof. [Код и первая неудача/новый результат][p-startup-status], [sampled96][p-await].

Здесь видны минимум две установки разных дельт (policy и handoff), installed review и semantic review; полный author/wait breakdown неизвестен.180 был дешёвым инженерным изменением относительно переписывания всего startup, но READY не отменил полезный generation gate. Поздний успех **не доказывает**, что только timeout5 был причиной первого FAIL3. Стоимость подготовки была отдельной от 92 s service. Обязательность каждого исторического промежуточного документа из данных не следует.

### Д 2. Source109: установлен, но подготовка лишила запуск времени

Astra R39 выполнила установку 109 и физическую проверку → native start admission после preflight нашёл≈242 s вместо 271 → **отказ до запроса service start**, R39 закрыт. Увеличивать service180 бессмысленно: этот timer ещё не начал отсчёт. Отдельная finite1800 s операция приняла уже установленный артефакт без reinstall → READY92,255021 s, generationPASS,0restarts, stop 70/watchdog 30 сохранены → genuine IANA fetch36,217 s и отдельный context 15,528 s. [Факты 109][p-actual109].

Web был partial: direct route сначала отказал, supported `tool_call` восстановил запрос; добавленная ложная дата осталась FAIL. Kimi проверила 9 cached joins, не читала raw live store и не покрывала поздний follow-up. Минимум одна установка, затем **один отдельный start без повторной установки**; точная стоимость preflight R39 и ожидания недоступна, известен только остаток. Полезен floor, сохранивший stop/proof; лишним оказалось планирование start из уже потраченного тесного окна. Решение приблизило результат, не ослабляя READY.

### Д 3. Длинная беседа: exact context → length →8192 → отдельная compression None

Первая проблема не была «мало секунд»: historical missing/null prompt/tool pins не позволяли exact manual context. Sol/Root C2 собрали текущую native authority из настоящих prompt/tool/core-memory builders без выдумывания исторических pins;20 affected controls, прежние 29 переиспользованы → Source103 установлен → genuine compact дошёл до summary, но non-stop output отклонён до commit, subtype ещё UNKNOWN. Source104 добавил ограниченную telemetry → реальный `finish_reason=length`,0 visible,4096 output,6350 prompt,40,018 s auxiliary/40,292 s whole;230 originals и flags сохранены. Защита не дала опубликовать пустое summary.

Source105 отдельно поднял допустимый reserve 4096→8192, сохранив schema 2048/context 40960/safety 1024 → доNone снова **length/0 visible**,103,913 s auxiliary/104,189 s whole; рост сам по себе отказ не исправил. Отдельное owner-согласованное `auxiliary.compression.reasoning_effort:none` применено через existing managed prepare/finish/CAS к root и tester profile; основной model/server/другие маршруты не меняли. Последующий native compact реально commit:230 originals сохранены,1summary,9active rows,18physical model calls,306,624 s. Старый 90 s observer остаётся NOT_ESTABLISHED. Далее DOCX revision/artifact и context прошли, независимый cached review 40 checks; отдельное XLSX чтение/arithmetic/context 56 checks. [Exact-context/ошибки/результаты][p-context], [None фактура][p-none].

Подготовка/installation отдельно: R32 settings шаг с 55 CPU s остановился после 2 из 8 config/seal изменений; reviewed same-transaction continuation с 240 CPU s завершил оставшиеся 6, сохранив original wall/reserve. Нет основания складывать CPU55+240 с model306,624 как calendar delay. История содержит последовательные 103/104/105 installations и отдельную policy adoption; точное число всех передач и время реализации не восстановлено. None оказался полезным ограниченным параметром,8192 в одиночку отказ только отложил. Hidden reasoning exhaustion — гипотеза, не измерение; driver/offload как единственная причина не доказаны, matched benchmark отсутствует.

### Д 4. Файл принят, а проверяющий потребовал чужой ID и ненужное слово

Source108 genuine fresh TXT → product прочитал собственную received copy, дал summary без synthetic contact literals → Root первоначально потребовал равенство send-ACK и native-user message IDs → это **разные namespaces**, требование снято по корректному join. Отдельная dependent CLI была запущена до создания scenario и отказала до send/consumed run; поздний настоящий запрос использовал ещё не использованный planned ID один раз. Затем Root ошибочно потребовал незаказанное слово про contact в корректном follow-up; правильный критерий — отсутствие самих contact literals. Повторной отправкой не «исправляли» уже полученный ответ. [Сохранённые preparation failures][p-actual109].

Итог:1243B upload/received bytes совпали, mode0600; summary28,103 s, отдельный context 9,231 s без нового чтения;271 previous bodies/flags retained; Kimi25cached checks. Один genuine upload и один follow-up; full 90+terminal custody Root-attested, lower-level raw poll не экспортирован reviewer. Это быстрый продуктовый путь с задержкой/ошибкой oracle, не доказательство продуктового дефекта. Точных минут исправления assertions и передач reviewer нет. Проверка физического файла и исключения contact полезна; equality чужих namespace и лишний literal были ошибочны. Аналогичный raw-vs-Markdown mismatch при XLSX чтении и ошибочный prose hunk-count7/8 у tester сохранены как ошибки подготовки, не скрыты как PASS.

### Д 5. Небольшой XLSX editor через композицию, отказ consumer и actual corrective install после `/new`

Source109 R41: genuine fresh XLSX прочитан, но обычный writer разрешил plaintext под `.xlsx`; readback malformed, в 90 s capture ответа нет, поздний persisted ответ предлагал иной legacy XML и неверно вывел отсутствие formulas из text projection → **реальный продуктовый FAIL**. Sol S153 сделал ограниченное own-workspace numeric-cell edit в новую копию, сохранив исходник/прочие ZIP parts/formulas/chart/defined names/zero IDs;64 author+37 independent, исправлены два review-дефекта. S154 портировал ровно четыре afterimages на genuine109:75 author+79 independent, прежние 64+37 не перезапускались;110 стал SOURCE_ACCEPTED, не live. [Source110 patch][p-xlsx-patch] и [границы][p-xlsx], [R41][p-power].

R43 до effect admission закрыт owner pause для обновления сессий. После `A-NEW` R44 новый actual external consumer завершился KeyError; isolated replay точного publication loop воспроизвёл lookup mode нового файла. В actual stderr traceback не было, поэтому реконструированную точную причину не объявляем непосредственно наблюдённой. Owned rollback сверил все 17 711 native Source109, configuration/credentials/data и прежние 321 message bodies сохранены. Generic project installer не меняли. Новый source-only S157 corrigendum исправил mode и отдельную recovery lineage; S158 проверил actual Root operation, затем bound request/envelope в рамках того же review clock. R44 FAIL/clock/journal не переписаны, R45 не его replay.

Безопасный exact expression из final external consumer `stage2/friday_ordinary_install.py`, SHA **`59adab0714b7567f0b59cf2bffc33cac05e3077190d5894702f6537a236fa052`**, внутри publication loop:

```python
# Был lookup physical_native_modes[row['path']] и для нового файла.
(0o644 if row['new_file'] else narrow_binding['physical_native_modes'][row['path']])
```

Новый файл не имеет beforeimage mode; existing files сохраняют captured physical mode. Полный surrounding path всё ещё проверяет manifest output SHA/bytes, `budget.check`, `prove`, directory custody и owned `publish(saved[name], owned, name)`. Для corrective predecessor требуется authenticate закрытый failed journal+rollback, новый explicit Root grant/clock, no-consumer, exact preserved history union; это не просто пропуск старого failed state.

R45 actual update rc0, **один installer attempt**, наблюдение вернулось не позже 36,648 s от dispatch (upper bound, не точная process duration). Root verifier3,264 s подтвердил итог из А 2. S157 elapsed1512,140 s включает implementation/review/continuation внутри 1800; continuation814,338 s — **часть** тех же 1512, не прибавлять. S158 Part1 326,313 s, финал 812,553 s — также вложены, не два полных периода. Видны четыре самостоятельных Sol назначения S153/S154/S157/S158 с возвратом результата Root; полное число TASK/CONTROL/RESULT передач и время реализации, ожиданий, публикаций и пересборок не сведены. Одна R44 неуспешная установка/rollback и одна R45 успешная отличны от source composition.

На последующей native-подготовке Root дважды исправила **собственные предположения о схеме до effects**: ожидала `subject` вместо `accepted_bound_verifier_ref`; искала actual input в `current_named_pins`, хотя он в stage2 `ROOT-USE.current_input`. Reviewer затем обнаружил ещё MEDIUM: preparer **и downstream caller** требовали ровно 8 полей backend-absence proof, actual pinned proof содержал ещё 4 честных metadata поля. Root минимально заменила whole-dict equality проекцией 8 обязательных смысловых полей; full proof hash, same boot/operation/PID/birth/no-successor/Root attestation/originalclock сохранены. Финальный caller/data review завершён 22:05:26, SHA **`d93bf06217b499b5068579cf9c5cbd5dd15b61160b04d6ac30dcf7877331fc56`**,0H/M: phase1 verifier, phase2a metadata finding+Root fix34isolated conditions, phase2b exact10data fields/11functions. Всё назначение 21:51:56–22:05:26 заняло 810 s в прежнем 900/reserve 60; это календарный elapsed source review, не чистое время чтения. Preparer завершился 0 и выпустил caller, затем Root dispatched его один раз после 24 CPU/unlimitedAS/remaining>613 checks. Это новая полезная проверка подготовки, не runtime defect XLSX.

Exact metadata correction `C/R45/BACKEND-PROOF-METADATA-COMPAT-DELTA.json`, проверенный полный SHA **`ad0f1eb21a2a6820c71ee18aba58018aae0bb6b4ce82c955f946c73d2c776015`**. Непосредственно прочитанный документ задаёт обязательные поля `schema,operation_id,current_boot_id,historical_boot_id,historical_pid,historical_birth,no_successor_identified,root_attested` и before/after code pins. Новый preparer SHA **`6c284f692340014cbf205f3c6439b3ffe45af6f97dfbf9a2b702e54456abcf38`**, caller template **`eb607a3c7e744dfc2ffcdab8d4f5e0605a271575a257d88b2ce175904e407acd`**. Приватные boot/PID значения здесь исключены. Подлинная изменённая левая часть сравнения: `{k: proof.get(k) for k in ('schema', 'operation_id', 'current_boot_id', 'historical_boot_id', 'historical_pid', 'historical_birth', 'no_successor_identified', 'root_attested')}`; правая часть по-прежнему содержит прежние exact expected значения, приватные ID исключены из публикации. Само исправление не доказывает service start; позднее фактическое выполнение установлено отдельным terminal из А 2. `no_successor_identified` — ограниченное местное наблюдение Root, **не полный census машины и не readiness**.

Результат приблизили узкий editor, consumer mode fix и honest corrective successor. Полезны CAS/rollback, физическая сверка и независимый downstream review. Потери видны в несовместимых producer/consumer и повторных bind assumptions. Установка 110 принята, native entry позже завершился 0 с original clock/reserve. Пользовательская XLSX-приёмка в срезе **ещё не состоялась**: новый заранее 180 s capture/deadline 300 dispatched ровно один раз 22:07:52, canonical tester завершился 2 с `UNKNOWN_SEND`, `send_state=unknown`, `send_attempts=1`, без ACK. Время dispatch→запись unknown около **10,00084 s**, что совместимо с whole-call ACK10 deadline, но **не доказывает точную причину**: `Runner.send except Exception` объединяет HTTP/transport failure и не сохранил исходный exception. По сообщению Root в 22:10 own-profileDB оставалась 321 messages, нового workbook phrase не найдено; отсутствие записи не доказывает неотправку в Telegram. Resend запрещён; новая read-only сверка допустима в уже разрешённой продуктовой работе, не ради отчёта. Gateway пока live Root-owned, cleanup в этом срезе не завершён. Worker/date/full baseline не блокируют XLSX, старые R41/R42/R43 результаты/окна не изменены.

### Д 6. Review остановило порчу процитированных дат

Source109 реальный web-ответ добавил устаревшую дату. Kimi B52 R1 искала первую текстовую пару start/date; R2 последнюю matching session date. Независимое ревью обнаружило MEDIUM: matching text может быть процитированными данными, не renderer-owned metadata; R2 19/23 controls, reject сохранён. B53 перенесла scanning в persistence, но Root две реальные отрицательные проверки quote-only/custom/timeless вновь получили 0/2: сам scan присваивал ownership чужому тексту. Final B53 отвергнут 0H/1M, не установлен.

B54 сменила гипотезу: origin ownership создаётся renderer, явно переносится через persistence/restore, legacy без sidecar остаётся честно stale до rebuild. Авторский RESULT:27/27 candidate и 4/4 baseline negatives; пять файлов. Native RESULT/RPC end_turn закрыты. Однако следующее независимое ревью исполнило реальные связанные функции и нашло новый MEDIUM; immutable `C/B54-INDEPENDENT/REVIEW.json` непосредственно прочитан, SHA **`d2ad050d98cad030d83c6354a8d7fd87c370b894760af5838f0671f504174de0`**, verdict `SOURCE_REJECTED_H0_M1`: `_seed_hygiene_system_prompt` переносит cached prompt без sidecar; `_rebuild_system_prompt_at_boundary` его сохраняет, но `_commit_compaction(in_place=True)` получает `date_ownership=None`, теряет persisted ownership, fresh restore остаётся со старой датой. Авторские 27+AST такой путь не доказали. Итог 17/19 independent controls: два failing assertions относятся к одной MEDIUM; авторские 27/27 и baseline4/4 воспроизведены отдельно. Review22:01:39–22:07:31 заняло 352,072 s. Root записала reject; receipt SHA **`9c4fbfa71af8f902bf10191d83ab26a8c92d22cb5b361ada8e7c073bdfb7fbcd`** сообщён интегратором, сам receipt здесь не перечитывался. B54 не accepted/notinstalled.

Минимум три последовательных авторских candidate assignments B52/B53/B54, внутри B52 две редакции и два отказа; точного общего времени и tokens нет. Возврат был оправдан изменением семантики собственности, а не стилем кода. Польза независимого review конкретна: не изменять цитируемые пользовательские данные и проверять реальную propagation, а не одно AST wiring. После двух одинаковых scan-отказов полезно сменили механизм; это не причина удерживать установку независимого XLSX. Полного публичного diff B52–B54 нет: этот вывод подтверждён непосредственно прочитанным безопасно изложенным отрицательным случаем с real SessionDB, полного внешнего воспроизведения без дополнительного обезличенного кода пока нет.

Сам reviewer тоже ошибался: первая проверка требовала day_rollover при trailer-enabled rotation, хотя unchanged runtime identity guard корректно rebuild для child Session ID; assertion исправлен по контракту, добавлен trailer-disabled continuing path, первый диагностический результат сохранён. Процедурное нарушение ресурса также не скрыто: широкие source copies временно заняли≈528 MiB allocated при 256 MiB disk cap, обе удалены и заменены Python-only копиями; итоговый logical output≈89,85MB, все тестовые процессы завершены, actual H/services/network не трогались. Это дефект исполнения review и cleanup, **не причина продуктовой ошибки даты**.

Проверяемый минимальный фрагмент причинной связки B54 из frozen candidate; пропуски обозначены `…`, условия при экспорте не исправлены. В `gateway/run.py::_seed_hygiene_system_prompt` реально переносится только prompt, затем выставляется флаг удержания:

```python
stored_prompt = ""
if isinstance(session_row, dict):
    raw_prompt = session_row.get("system_prompt")
    if isinstance(raw_prompt, str) and raw_prompt.strip():
        stored_prompt = raw_prompt
agent._cached_system_prompt = stored_prompt
agent._retain_seeded_system_prompt = True
return bool(stored_prompt)
```

В `agent/conversation_compression.py::_commit_compaction` (in-place) вызов изменён так:

```python
agent._session_db.update_system_prompt(agent.session_id, new_system_prompt,
                                      date_ownership=getattr(agent, "_date_ownership", None))
```

В `hermes_state_sessions.py::update_system_prompt` ветка отсутствующего `ownership` удаляет carrier в той же транзакции:

```python
else:
    conn.execute(
        "UPDATE sessions SET model_config = json_remove(model_config, '$." + DATE_OWNERSHIP_FIELD + "') "
        "WHERE id = ? AND json_type(model_config, '$." + DATE_OWNERSHIP_FIELD + "') IS NOT NULL",
        (session_id,),
    )
```

Наблюдение реальных SessionDB/commit: валидный sidecar до seed → `in_place_committed` → carrier отсутствует → fresh restore сохраняет прежнюю дату, без `day_rollover`. Для идентификации этих трёх исходников, соответственно: `gateway/run.py` SHA `748a0b54335e14cbc3225b9591222c57e01672d631d4f385955573141ab9cddb`; `agent/conversation_compression.py` SHA `ccb426fb5d17fa906bded19c1ef3cb30e58ecb660b9619cf5c95d647dea6fc7d`; `hermes_state_sessions.py` SHA `422bf4b1122c985a2e2184cb40c3d3fe6cf799731aa960a7a358611c6fb17d1d`. Это доступный кодовый фрагмент причины, а не обещание полного публичного test environment.

### Д 7. Worker declarations: полезные findings и настоящая незавершённая registration

Изначальный worker-source candidate имел 13 isolated checks, но независимый S156 нашёл две причины: direct API мог получить новый/расширенный Budget; staged launcher/downstream lineage не был согласован с migration. Авторский child исправил оба целиком →36 author+24 independent,0H/M;52 unchanged validator decisions и 25 supplemental переиспользованы. Budget теперь связывает original origin/seconds/deadline до IO/effects;0400staged launcher входит в тот же owned CAS/rollback набор, actual downstream `staged_sources` и ordinary-inspect проверены. [Публичный полный шестифайловый patch][p-worker-patch], [manifest][p-worker-manifest].

Но исторический A0 registration **успешен и inactive**, с immutable старым launcher receipt. В installed среде read-only поиск обнаружил этот retained prefix; marker `a0_service_receipt_sha256=null` не означает отсутствия истории. Candidate честно отказывает до effects. Отдельный 331,955 s source-analysis установил: поддержанного перехода к новым declarations в существующем maintenance ещё нет; простое снятие guard небезопасно. Нужен finite retained-success branch с сохранением старого evidence и отдельной current-source receipt/lineage, затем future ordinary ancestry bridge. Sol S159 получил связный source-only пакет после одного native compact; runtime/registration ещё не приняты.

Время remediation949,366 s в отчёте **консервативно начисленное**, не точное физическое: acceptance time неизвестно, начальные 240 s чтений учтены с запасом; записанное 709,366 s — от позднего clock record. Это не равно дополнительной задержке XLSX. Полезны оба review findings и refusal исторического receipt; долг — отсутствие нужного transition, а не нехватка ещё одного approval. Обычные файлы/диалог от workers не зависят; полного worker gate source patch не прошёл и не должен притворяться прошедшим.

### Д 8. Closed rejected Kimi result перестал запрещать следующий compact

Старый `command_compact_request` требовал `terminal_reason == accepted_result`, хотя задача уже корректно закончилась rejected result. Это смешивало завершённость задачи с качеством её кода и мешало новому назначению. Узкий [host patch][p-kimi-patch] разрешил accepted/rejected, для rejected требует именно lead receipt `rejected`. Сохранились task/epoch/session binding, отсутствие evidence warnings, `result_ready`, exact result ID, idle/no effects, genuine task turn и отдельно подтверждённый native compact.

Наблюдаемое применение после rejected B53: result received/consumed/rejected, genuine native turn end; compact той же `K-SESSION`, затем B54, не `/new`. Это повторное самостоятельное назначение, не продолжение отвергнутого B53 и не его повторная приёмка. Приватный compact record даёт cursor/request/session joins; raw wire может содержать скрытые рассуждения и не публикуется/не читается для досье. Точных elapsed compact/receipt costs в выбранных материалах нет. Здесь убран именно лишний accepted-only predicate; полезные guarantees завершения/идентичности/контекста сохранены. Не следует из этого удалять весь Kimi lifecycle или возвращать отменённый Astra/Sol обвес.

### Д 9. Что можно и нельзя сказать о цене

В выборке есть отдельно измеренные 15,4385 s composer,4,271 s source scan,43,507/64,047 s конкретные установки,38,795 s установленная проверка,3,264 s R45 verifier,92–94 s READY,28,103/9,231 s TXT и 306,624s18-call compact. Это разные операции разных кандидатов. Для доли «бюрократия/разработка» нет общего знаменателя и непрерывного учёта активной работы, queue wait, owner interruptions и инфраструктуры; **процент не вычислялся**. Нет достоверной денежной оценки и task-level token accounting. Исторические goal counters не раскладывают эти случаи по причине расхода; cached input нельзя считать бесплатным/нулевым, reasoning нельзя игнорировать в output.

Потеря питания и recovery local inference22.10 — внешний перерыв; обновление сессий — отдельное owner поручение. Их полное время не измерено и не записано как простой инженеров. Отсутствие коммитов между публикациями не означает бездействие. Пока Root связывала R45, Sol и worker/date reviewers работали параллельно; сложение их elapsed завысило бы календарную задержку.

## Е. Ревью и «горячая картошка»

Единого owner-запрета reviewer исправлять любой дефект в прочитанных актуальных материалах нет. Фактический write scope конечного задания обычно ограничен своим review directory; например S158 требует exact operation review, затем CONTROL final-bound review, запрещая product/main/`H` effects. Такой reviewer не может молча изменить чужой frozen source и назвать прежнюю проверку независимой. Это контракт назначения, а не неизменяемая архитектурная необходимость. Глобальный reviewer-fix пока **предложение**, не внедрённый регламент.

Документированного случая «reviewer уже имел готовый полный правильный diff, но его обязательно вернули автору только для перепечатки» в просмотренной выборке нет. При B52→B53→B54 возврат обоснован изменением происхождения ownership и propagation; готовый безопасный однострочный scan-repair не существовал. В R45 Root сама исправляет свои однозначные bind expectations и metadata predicate; другой reviewer проверяет изменённый seam. Это ближе к короткой инженерной петле, но не доказательство принятого общего reviewer-fix процесса.

Рабочий кандидат на упрощение: reviewer с заранее расширенной **конкретной** write scope исправляет однозначный локальный дефект → фиксируются его точные bytes/авторство → первоначальный автор или другой участник проверяет новую логику и затронутые связи → Astra интегрирует. Собственная проверка reviewer не считается независимой проверкой его дельты; обязательного третьего участника нет. Для текста достаточно фактического source/contract read; для допустимого metadata состояния — positive плюс meaningful negatives; для файловой операции — new/existing/mode/CAS/rollback; для auth/data — origin/foreign/stale/isolation; для install/cancel — actual owned-process и recovery. Число строк не определяет риск.

Контракт oracle задаётся owner scenario/catalog и исходным запросом до теста. Исправление неверного literal/ID/Markdown ожидания должно быть объяснимо независимо от результата и сохранять исходный отказ. Изменение окна/ожидаемого смысла после send не исправление oracle, а подгонка; новый заранее объявленный эксперимент сохраняет старый исход. Проверяющий не вправе менять запрос так, чтобы исчез нужный пользовательский риск.

## Ж. Технический долг, критический путь и адресные предложения

Ниже **предложения для внешней коррекции**, а не новые обязательные orders/gates. Точные минуты экономии неизвестны; ожидаемый результат выражен сокращением действий/возвратов.

| Существующее решение / предложение | Польза и конкретный шаг | Риск / сохраняемая гарантия / минимальная проверка / возврат |
|---|---|---|
| Сохранить pinned donor/layers/owned CAS/rollback | Они реально обнаруживают drift и восстанавливают R44. Не заменять новый framework. | Менять их только при конкретном дефекте; повторное review source только при byte/dependency change, свежие mutable-state checks перед effects всегда. Возврат — имеющиеся exact beforeimages/journal, не второй installer. |
| Устранить особый final entry для стандарт 180 | В существующих `friday_start.py`/clean-environment callsites явно проводить уже принятое 180; историческое имя `TEST` и ambient-strip сейчас требуют помнить отдельный путь. | Не менять server/model/watchdog/stop; проверить last-entry env, generated/loaded unit180, full command 210/proof 60/identify20 и refusal при нехватке. Вернуться к последнему проверенному native recipe, не автоматическому 90. |
| Проверять producer/consumer на настоящем schema до materialization | В existing Source92/95 feature adapters сверять exact request/frozen/core/manifest на реальном закрытом input до тяжёлой операции. Это предотвращает `frozen.input`, `subject` и `current_named_pins` false assumptions. | Не универсальный schema registry и не fictitious fields. Positive actual input + missing/foreign/stale negatives; исходные helpers/pins сохраняются для возврата. |
| Переиспользовать unchanged source, отдельная final data binding | Сохранить S158 pattern: неизменный S157 source reused, проверить новую operation и позднее только exact bound tuple. Публикация не перезапускает продуктовые suites. | Два этапа нужны, когда действительно меняются authority/data/bound bytes; не два полных повторных ревью. Проверять diff/literals+hash/current CAS; при изменении логики вернуть review соответствующей области. |
| Убрать whole-dict equality для разрешённой observational metadata | Ограниченно повторить R45 correction: обязательные semantic поля + полный pinned proof hash вместо запрета четырёх честных metadata полей. | Не принимать произвольное расширение auth/request schema. Negative missing/wrong semantic fields, boot/owner/clock; при неожиданном поле с полномочиями refuse. Вернуть конкретный before helper/pin без стирания observation. |
| Mode новых файлов и exact inventory вычислять по manifest delta | В existing external consumer new-file branch0644, existing-file capturedmode; общие total counts сверять с parent+declared adds, точный набор/hash сохранять. | Новый режим нельзя брать из отсутствующего beforeimage; проверить create/oldmode/foreign drift/rollback. Parent snapshot остаётся rollback point. Не снижать integrity до одного count. |
| Не ждать связки несвязанных исправлений | XLSX110 можно довести независимо от worker/date/full baseline; source worker/date публиковать с честным статусом. | Изоляция зависит от реальной disjoint области, а не названия задачи; проверить состав diff/dependencies. При общей изменившейся зависимости проверить её, не всю лабораторию. |
| Reviewer-fix для локальных определённых находок | Выдать writer scope на конкретный файл/hunk только когда reviewer берёт fix; другой участник проверяет дельту. Уменьшает handback при сохранении независимости. | Не разрешать silent edit frozen author artifact; authorship/afterhash обязательны. Файловые/auth/stop seams требуют соответствующих controls. Возврат — original author variant с сохранённым review. |
| Довести retained inactive registration в существующем maintenance | Sol S159: сохранить old successful inactive receipt, создать current successor + ordinary ancestry; не заставлять пользователя удалять markers руками. | Это code gap, не «ещё одно одобрение». Нужны retained-success positive, historical no-replay, foreign/active stale negatives и staged downstream. Existing history immutable, эффекты отдельно допускаются после source acceptance. |
| Сохранить диагностическую причину UNKNOWN_SEND безопасным enum | В существующем `Runner.send` terminal record отделять известный local deadline/HTTP/transport phase без raw exception, ключей или body. Нынешние≈10 s позволяют гипотезу, но catch-all уничтожает причину. | Состояние доставки остаётся UNKNOWN, права на resend не появляется. Минимальные existing-code checks: deadline/HTTP/transport и secret-bearing error дают разные фиксированные safe labels; bytes/custody не меняются. Возврат — прежний terminal schema/код, старый UNKNOWN не переписывать. |
| Сохранить site-specific adapters, сокращая копии | Нынешний exact PM/private-parent exception и wrappers допустимы на текущем host, если pinned/documented/recoverable. Объединять только доказанно одинаковые части existing helpers. | Сигнал пересмотра: очередной backendproof/schema/mode отказ того же класса или port на другой host. Не строить universal installer перед показом; положительный реальный input и значимые negative boundaries, rollback к старому recipe. |
| Явные names для вариантов одного Source | Source99 helper-only и integrated-core99, Source105 до/послеNone имеют разные identities. В существующих status использовать variant+input+receipt, не rebase всех альтернатив. | Сохранять ancestry/pins; новый variant не наследует live evidence автоматически. Проверка — exact composition provenance; возврат к последнему verified receipt. |
| Отдельно показывать помощь оператора и работу Friday | Root отправляет fixtures/проверяет файл, но не должен вручную подменять запрошенный output. Явно учитывать tester sends, owner reboot/ручные шаги и product tool result. | Нельзя выдавать инженерный direct-tool/изменённый файл за пользовательский путь. Проверять persisted request→product tool→downloaded hash→reply/follow-up. Нового telemetry collector не нужно. |
| Часто меняющийся status обновлять дельтой | В existing README/STATUS один current installed/runtime pointer, старые snapshots явно исторические. Сейчас Source110 source README после R44 отстаёт от actual R45. | Не переписывать историю и не stage ownerdirty foundation-status. Проверка публикационного current pointer против final receipt; вернуть прежний public checkpoint, оставив новую дельту как unknown если доказательства неполны. |

**Критический путь позднего среза:** native caller/data review закрыт, standard180 entry0 уже выполнен; теперь адресно сверить **UNKNOWN_SEND без ACK**, сохранив единственную попытку и original R45 clock/stop 70/Root reserve 180 → получить достоверный пользовательский XLSX-результат в разрешённом новом действии только после установления эффекта прежней отправки → физически проверить ZIP/cell/formulas/исходник/delivery/persistence → отдельный natural contextual follow-up → фактически остановить/передать ownership по операции. Если поздний budget admission откажет, честно закрыть этот исход; не переназвать истёкший clock. Необходима Astra как sole operator/tester; reviewer изменённого prepare/caller seam своё назначение уже завершил. Sol worker succession и Kimi date fix идут параллельно. Не нужны новый `/new`, общая worker qualification, дата B54, полный baseline или публикация этого отчёта как разрешение обычного XLSX. Текущая инфраструктурная готовность должна быть установлена в разрешённой продуктовой работе; исторический READY не заменяет её.

## З. Доказательная карта, противоречия и пробелы

Все GitHub-ссылки ниже закреплены на **`64e74601d72b56fd92506e167462b19f068f8b4f`**, а не на подвижный `main`. Местные хеши идентифицируют прочитанные файлы, но публичное основание каждого существенного местного вывода дано содержанием/excerpt выше. Local path без доступного файла не объявлен внешним источником.

| Вывод → версия/место | Фактически проверенный объём | Предел |
|---|---|---|
| Policy180, separate generation failure, identify20 → [README/validation][p-startup-status], [generation diff][p-generation] | Подлинный public code, author/independent summaries и реальные timings/FAIL/initial smoke. | Не matched causal proof всех startup отказов и не нынешний boot READY. |
| Source96 наблюдения → [OBSERVATIONS][p-await], [Source90 diagnostic][p-diagnostic] | Sample chains,14spans/36,468 s, source scan cost, owned stop; limitations прочитаны. | Нет полного caller/count/thread-time; нельзя всё 90 s списать на guard. |
| R39≈242<271, later1800/start без reinstall, TXT oracle errors → [actual109/status][p-actual109] | Все перечисленные fields, scoped latency/cached-review limits; current source patches рядом. | Raw transcript/cursor/file body закрыты; Root live custody не независимо повторена. |
| Compression chronology/settings/None/user result → [status][p-context], [None][p-none], [8192 diff][p-8192] | Разные 103/104/105 состояния и original FAIL, actual length/zero-visible, commit230/18calls/306,624 s, scoped document results. | Hidden reasoning/token billing, synthetic date answer и driver causality неизвестны. |
| Schema mismatch → [consumer entry diff][p-schema]; public ordinary updater functions | Exact old/new frozen-shape predicate и реальные hardcoded fields/counts в коде. | Private adapter общая история не полностью опубликована; excerpt не весь consumer. |
| Source110 → [patch+manifest][p-xlsx-manifest], public R44 summary, R45 selected acceptance/external mode excerpt | Exact four-file identities/prerequisites; напрямую прочитанные actual acceptance fields/full SHA; R45 once update и rollback history preserved. | Current public source 110 README ещё говорит not installed послеR44. Последний actual R45 имеет приоритет по **installed**, но не доказывает live. Полный 17712receipt private. |
| S157/S158 → private RESULT/OPERATION/ROOT-USE exact cached pair | S15712engine+26helper+7producer groups (fixtures), old13+33 reused; S15849parent+two review reports, original elapsed/pins/limits. | Не доказательство независимого installed/live; task/result state исторически source-only. |
| Worker source и inactive gap → [worker README][p-worker] / [patch][p-worker-patch], [manifest][p-worker-manifest]; local retained-registration RESULT | Полный 6-file diff,36+24 и reuse52+25, конкретный retained-success unsupported transition; честные source/runtime flags. | Existing controls synthetic authority/TLS adapters; current `H` authority и registration не приняты. |
| Rejected Kimi compact → [host patch][p-kimi-patch], current local helper SHA/excerpts | Predicate/receipt-state delta, unchanged native completion/session/cursor/checkpoint checks, post-B53 use reported Root. | Полный private wire не экспортирован. Duration/token use compact неизвестны. |
| B52/B53 corruption и B54 real-propagation finding → private selected final/result + Root message | Прочитаны B54 author final и exact independent review `d2ad050d…`:5 files/27 author/4baseline,17/19 independent с одним material finding; seed→rebuild→inplace commit→restore negative и reviewer corrections/overrun. | B54 source rejected/notinstalled; full bounded-manual native не исполнялся. Для полного внешнего воспроизведения нужен safe code/fixture, не скрытые мысли; локальное содержательное доказательство изложено в Д 6. |
| Session refresh/current rules → private owner paste/handoff, ROUTE-VERIFIED/RESTORED/ACTIVE-GOAL | Exact instructions safe excerpt, times20:28/20:30, new model/goal/state, protected Sol route. | `AGENTS.md` в checkout отсутствует; полная передача внутренней памяти не наблюдаема. Historical scope/model text не current authority. |

Противоречия, которые важно сохранить видимыми:

1. В старом goal/`GOAL_SCOPE` указаны Astra gpt-6-astra/FastOFF и прежние «ждать второй Sol report», тогда как поздние owner paste/native settings требуют 6.1-sol/ultra и продолжают работу после verified restoration. Позднее указание выше; файлы сохранены как история.
2. В session knowledge map старые поля `S158.native_latest=inProgress`, `S159 compact not yet verified`, `B54 no final yet` могут соседствовать с поздними received/consumed результатами. Для текущего состояния важны latest delta + exact immutable result, не произвольное первое совпавшее поле. Parent подтвердил S159 compact/TASK около 22:00 и genuine B54 end_turn.
3. Public Source110 README корректно фиксировал R44 rollback/notinstalled в момент своего checkpoint; actual R45 позднее установил 110. Не переписывать R44 как success и не выдавать старый README за последний installed факт.
4. Tester `advance` есть в CLI, но bounded final branch запрещает его. Поиск одного имени функции и требование «довести capture доPASS» ошибочны.
5. Наличие `lifecycle` в старом каталоге/комментарии/TASK не доказывает активный Astra/Sol controller; основной sender owner-removed branch использует native RPC. Kimi current lifecycle имеет отдельный 20.10 источник и смысл.
6. Исторический 0rc внешней оболочки/cleanup не отменяет inner native FAIL3; source green не отменяет product FAIL; observer UNKNOWN не уничтожает отдельно проверенный delivered artifact. Статусы должны читаться с scope.

Существенные неизвестные:

| Пробел | Что нужно для вывода; можно ли взять из существующего |
|---|---|
| New Source110 XLSX/runtime result | Native entry0 установлен отдельным terminal, новая отправка UNKNOWN_SEND/noACK; нужен будущий наблюдаемый user/artifact/context результат и actual stop, не повтор неизвестной отправки. Installation acceptance исторически сохраняет NOT_RUN. |
| Полный external reproduction installed110 и private helpers | Существующие receipts/код есть локально, но полный dump небезопасен. Для спорного конкретного вывода можно передать владельцу ещё один минимальный обезличенный diff/fixture; данный отчёт не утверждает доступность всей private установки. |
| Полное внешнее воспроизведение B54 | Immutable review уже прочитан и reject установлен; минимальный безопасный executable fixture/diff пока публично не размещён. Это существующий материал для адресной redaction, не повод повторять модельные запуски. |
| Полный current infrastructure readiness | Late native terminal даёт scoped gateway ownership, но не полный inference/worker/release health; prepower и metadata200 недостаточны. Нужен продуктовый observed result, досье его не создавало. |
| Exact author/queue wait/publication/owner interruption costs | Частично могут быть в существующих clock/receipt metadata; полного attribution нет. Не читать полные model histories и не строить collector ради процента. |
| Money, complete model tokens/reasoning/cache split | Имеющихся goal counters/task records недостаточно; нужны реальные usage/billing источники, если владелец решит это исследовать. UNKNOWN не 0. |
| Единственная причина 90 s/generation/driver delay | Existing samples не идентифицируют всё; нынешние scoped successes не causal experiment. Новый benchmark в эту ревизию не входил. |
| Universal reviewer-fix rule и ненужные отчёты по всей истории | Правила нет, полной corpus-инвентаризации не было. Есть конкретные конечные TASK write scopes; адресное изменение возможно без нового approval hierarchy. |

Подготовка досье не вводит ни одной новой обязанности перед следующим продуктовым действием. Его публикация — материал для внешнего анализа, не release acceptance и не новая точка owner approval.

**Последний включённый продуктовый срез:22.10.2026,22:11 МСК. Подготовка завершена: 22.10.2026 22:15:12 МСК; фактическое время от первого чтения: 14 мин 8 с.** До публикации интегратор может добавить более позднюю фактическую дельту с отдельным временем; она не изменит исходы исторических случаев.

### Дельта интегратора перед публикацией — 22.10.2026 22:18:32 МСК

Эта дельта имеет приоритет для текущей доступности; исторические исходы и timestamps выше сохранены.

**Cleanup завершён:** `C/R45/POST-TG-STOP-TERMINAL.json`, SHA `efacfa4e5569e48e5b6b74e2cfdafa011a8753aa9a7285deae82f21f7f56c501`: `EXACT_OWNED_STOPPED`, stop returncode0, **0,79757 s**, original workcut/reserve сохранены. Перед stop сверены новые boot/invocation/PID/birth/UID/executable identity/cgroup и отсутствие чужой job; после — существующий quiescent reader. Исторический PID не использован как current custody. **Source110 установлен, gateway STOPPED, workers OFF; новый XLSX не принят, полного READY/релиза нет.**

К **22:14:50** read-only observation собственного профиля всё ещё давала 321 сообщение, ноль строк с новым именем копии и прежний последний timestamp. Это отсутствие подтверждения, **не доказательство неотправки в Telegram**. Исходный общий deadline уже истёк; ACK не получен, поэтому post-ACK receive window не открылось и не выдаётся за полностью пройденное.

Root подготовила отдельный текстовый запрос о получении/уже готовой копии с запретом новых правок. Canonical CLI отказал за **0,0197 s** до создания нового run и любого HTTP/send: `Runner.new` блокирует всю новую работу при статусе вне `EVIDENCE_READY/STOPPED/FAILED`, а также при `send_state` равном `intent/unknown`. Стандартный entry перед этим локально читает credential под lock; отсутствие HTTP не означает отсутствия этого чтения. Исправление терминологии Root: текст «только проверь» всё равно `sendMessage` и способен вызвать действия продукта, а не чистое чтение. **Второй Telegram-запрос фактически не отправлен; повторной правки не было.**

Отдельный конечный продуктовый source-only пакет существующего tester готовит узкий `reconcile-unknown`: один authenticated `getUpdates` по pinned cursor после старого deadline, без cursor/run mutation, send/getFile/download. Наблюдения — карантин, связь с исходной операцией UNKNOWN, acceptance не установлена. Это пока **разработка**, не принятый/установленный обход; старый run, attempts, исходные часы и UNKNOWN не переписываются. Пакет не требуется для публикации досье и не является новой системой проверок.

B54 окончательно rejected по одному M; B55 выдан в тот же Kimi-сеанс после одного фактически завершённого native compact (**50,796 s**). B54 clock закрыт, новый B55 clock включает свою подготовку/compact; общего повторного `/new` нет. S159 Сола продолжает source-only участок. Ни дата, ни workers не блокируют обычный XLSX.

**Уточнённый критический путь:** безопасно разобраться с неопределённой Telegram-отправкой без повторения неизвестного эффекта; затем получить настоящий пользовательский артефакт и follow-up. Повторная установка принятого Source110 для этого не нужна. Полномочия, активная goal и уже разрешённая автономная работа сохраняются. Подготовка первого досье заняла 14 мин 8 с; поздняя интеграционная дельта и публикация учитываются отдельно, параллельная продуктовая работа не объявляется простоем.

[p-startup]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/startup-policy-one180-installed96-20261022/README.md
[p-startup-status]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/startup-policy-one180-installed96-20261022/validation.json
[p-generation]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/startup-policy-one180-installed96-20261022/generation-handoff.patch
[p-await]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/startup-await-observation-source96-20261022/OBSERVATIONS.json
[p-diagnostic]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/checkpoints/2026-10-21-ordinary-startup-causal-diagnostic/RESULT.json
[p-actual109]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/ordinary-user-functional-repairs-20261022/actual-jarvis-source109/status.json
[p-power]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/ordinary-user-functional-repairs-20261022/actual-jarvis-source109/postpower-and-document-delta.json
[p-status]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/ordinary-user-functional-repairs-20261022/STATUS.json
[p-context]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/ordinary-user-functional-repairs-20261022/source-context-corrections/status.json
[p-none]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/ordinary-user-functional-repairs-20261022/source-context-corrections/compression-none-current-site.json
[p-8192]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/ordinary-user-functional-repairs-20261022/source-context-corrections/auxiliary-working8192-schema2048-source105.patch
[p-schema]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/startup-two-flush-await-bounds-source95-20261022/consumer-entry-schema-review.patch
[p-xlsx-patch]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/ordinary-user-functional-repairs-20261022/accepted-own-copy-xlsx-source110/accepted-own-copy-xlsx-cell-edit-source110.patch
[p-worker-patch]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/ordinary-user-functional-repairs-20261022/accepted-worker-declarations-source-only/worker-declarations-complete.patch
[p-xlsx]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/ordinary-user-functional-repairs-20261022/accepted-own-copy-xlsx-source110/README.md
[p-xlsx-manifest]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/ordinary-user-functional-repairs-20261022/accepted-own-copy-xlsx-source110/accepted-own-copy-xlsx-cell-edit-source110-manifest.json
[p-worker]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/ordinary-user-functional-repairs-20261022/accepted-worker-declarations-source-only/README.md
[p-worker-manifest]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/ordinary-user-functional-repairs-20261022/accepted-worker-declarations-source-only/MANIFEST.json
[p-kimi-patch]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/ordinary-user-functional-repairs-20261022/host-rejected-result-compact.patch
[p-tester-patch]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/docs/review-candidates/ordinary-user-functional-repairs-20261022/actual-jarvis-source109/tester-S147-B48-cumulative-from-canonical-R2.patch
[p-composer]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/scripts/hermes_prepare.py
[p-install]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/scripts/friday_install.py
[p-ordinary]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/scripts/friday_ordinary_install.py
[p-budget]: https://github.com/alinescafs3mp-afk/friday_rework/blob/64e74601d72b56fd92506e167462b19f068f8b4f/plugins/friday_rework/runtime_containment.py
