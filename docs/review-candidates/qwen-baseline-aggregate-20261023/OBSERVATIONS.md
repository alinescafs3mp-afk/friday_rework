# Агрегатные наблюдения Qwen

Исполнения: 23.10.2026, 22:24:06–23:05:41 МСК, с отдельным интервалом исправления инфраструктуры. 15 канонических исполнений, 12 разных заданий, 58 модельных вызовов. Повторы не добавляются к знаменателю разных заданий; четыре developer seeds и один внешний warmup в score не входят.

| Блок, по 4 разных задания | Машинный PASS | После внешней оценки прозы |
|---|---:|---:|
| Русский / рассуждения | 1/4 | 3/4 |
| Coding: завершённый сценарий | 1/4 | 1/4 |
| Agentic | 3/4 | 3/4 |
| Всего | 5/12 | 7/12 |

Исходные машинные статусы первых 12: PASS 5, PARTIAL 3, BUDGET_EXHAUSTED 3, TOOL_ERROR 1. После внешней оценки Codex: PASS 7, PARTIAL 1, BUDGET_EXHAUSTED 3, TOOL_ERROR 1. Исходные labels не перезаписаны. Отсутствие других классов отказов в малом наборе не доказывает отсутствие ложных утверждений или общую стабильность.

Код всех четырёх coding-заданий проходит исполняемые проверки. Два coding-сценария исчерпали число model turns до нормального окончания; третий завершился TOOL_ERROR из-за model-requested timeout вне схемы. Они остаются неуспешными end-to-end исходами: 1/4, а не 4/4. Третий BUDGET_EXHAUSTED относится к agentic-сценарию. Такие ошибки клиент не исправлял за модель.

Повторные якоря: три PASS в итоговом compatibility view; один из них (A2) первоначально получил WRONG_RESULT из-за ошибки recognizer. После posthoc исправления evaluator он переоценён офлайн в PASS по прежним trusted observations, без новых модельных или shell-исполнений. Исходный WRONG_RESULT сохранён. Повторы cache-eligible, sandbox сбрасывался; A2 показывает вариативность, поскольку исходный запуск остался BUDGET_EXHAUSTED.

Отдельная первоначальная попытка первого coding-сценария v1 остановилась на инфраструктуре: nullable SSE tool delta и пустой HTTP 200 abort ACK обрабатывались неверно. Попытка и первоначально неизвестная очистка сохранены; поздняя native/read-only проверка подтвердила отсутствие активной нагрузки. После client/adapter fix повторён только затронутый сценарий, без второго warmup. Не затронутые русские задания переиспользованы.

Вторая коррекция изменила только распознавание реально исполненной проверки в составном stdout. 39 локальных положительных/отрицательных controls прошли; независимое source-review Root не оставило HIGH/MEDIUM. Новых model calls для posthoc пересчёта нет. Prompts, fixtures, рубрики, пороги, бюджеты и порядок не менялись. Эти изменения после получения ответов раскрыты; это derived comparison view, не новый запуск.

| Версия / метрика | Значение |
|---|---|
| Набор / evaluator | `1.0.0-compat3` |
| Manifest compat3 SHA-256 | `887ba6f21336ee5294f98666f8e322c3263c2c517e82bfcc4d3288336a0294f9` |
| Execution manifest compat2 SHA-256 | `1fd45bcedc997127c9b4b99506ba1109e1d9b69c82aa881d4994a46ef7990e73` |
| Manifest v1 SHA-256 | `964782c0d8b3529fd5d917099568c8c616fdd9935940ca22a22452fd4d4debc3` |
| Модель | `qwen38-flash-next-abliterated`; Qwen3.8-Flash-Next-ABLITERATED-NVFP4 |
| Runtime | SGLang `0.0.0.dev1+g4ccff141d` |
| Runtime Git SHA | `4ccff141dbe992794f9da6c3aa23535b4f72000d` |
| Runtime image SHA-256 | `2d03c87699f2fec9b7d15cb28e8c3af2a65417a769bf773b7e9fb87d07e22eba` |
| Сумма task wall всех 15 / первых 12 | 1 574,79 / 1 364,31 секунды |
| Generated tokens всех 15 | 46 578, включая reasoning |
| Длинный контекст | Один сценарий; actual prompt 26 309 токенов |

Это фактически работавший runtime с локальными изменениями; Git SHA и образ не заменяют полный fingerprint. Полные веса не хешировались: известны checkpoint identity и hashes малых config/index metadata. Использовался один и тот же runtime до/после. TP1, NEXTN/MTP 3 шага/topk1/draft4, context 262 144, chunked-prefill 8 192, max-running-requests 2; embedding 4B/2560 оставался resident. Настройки для теста не перестраивались.

Thinking ON, preserve_thinking=true, temperature 1, top_p 0,95, top_k 20; output ceiling 8 192 токена вместе с reasoning. Клиентский concurrency 1; на agentic-case максимум 6 model turns, 12 tools, 16 384 generated tokens, 600 секунд wall и 120 секунд inactivity. Код исполнялся в изолированных bubblewrap sandbox; два agentic-сценария использовали симуляцию внешних эффектов. Они не являются проверкой реального внешнего хранилища или установки пакетов.

Суммы task wall не равны календарной длительности. E2E token rate определяется как reported completion tokens / полный model-call wall; это не engine decode. Engine decode unavailable, неизвестные cached-поля сохранены как null. Reasoning входит в completion, cached input входит в input. Скорости вывода и быстрое незавершение не заменяют качество. Статистическая значимость, p95 и универсальное превосходство не заявляются.

В 23:06:49 МСК подтверждены завершение/cleanup всех 58 stream, очистка всех 15 sandbox, здоровый runtime и native running/waiting/pending = 0. Это наблюдение в конкретный момент, без заявления о глобальном владении всеми jobs. Две ресурсные выборки не определяют peak memory, температурную траекторию или отсутствие throttling/interference.

Digest приватного отчёта: `335500100fd83e8eeda83f1149bc3963246e23928d2a53dc265d7213fa615fce`; агрегатов измерений: `f2f5fcefee4aaca459796acc14c2d1fd85efcfb27521ba0997b3791c6fd90f40`. Сырые материалы и внутренние адреса исключены из публикации. Baseline завершён, Product READY не заявлен; Ornith ещё не запускался.
