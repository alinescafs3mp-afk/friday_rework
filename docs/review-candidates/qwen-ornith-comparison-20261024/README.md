# Qwen / Ornith: один замороженный набор

По 12 разным задачам: Qwen **5/12** машинных PASS, **7/12** после исходной рубрики; Ornith **2/12** и **3/12** соответственно. Внешние оценки Codex не слепые. Астра независимо проверила прозу, итоговые результаты, одинаковые исходные задания/инструменты и сохранность замороженного набора; исходные labels оставлены без изменений.

| Задача | Qwen: исходный→с рубрикой; wall | Ornith: исходный→с рубрикой; wall |
|---|---|---|
| R1 | PARTIAL→PASS; 96.37 с | PARTIAL→PASS; 38.55 с |
| R2 | PARTIAL; 276.21 с | WRONG_RESULT; 125.30 с |
| R3 | PASS; 13.89 с | WRONG_RESULT; 23.34 с |
| R4 | PARTIAL→PASS; 242.25 с | WRONG_RESULT; 145.82 с |
| C1 | PASS; 138.67 с | BUDGET_EXHAUSTED; 246.63 с |
| C2 | BUDGET_EXHAUSTED; 113.20 с | BUDGET_EXHAUSTED; 141.55 с |
| C3 | BUDGET_EXHAUSTED; 165.38 с | BUDGET_EXHAUSTED; 457.30 с |
| C4 | TOOL_ERROR; 163.71 с | BUDGET_EXHAUSTED; 270.30 с |
| A1 | PASS; 32.58 с | PASS; 66.79 с |
| A2 | BUDGET_EXHAUSTED; 18.91 с | BUDGET_EXHAUSTED; 144.81 с |
| A3 | PASS; 68.71 с | BUDGET_EXHAUSTED; 77.46 с |
| A4 | PASS; 34.45 с | PASS; 49.30 с |

| Блок | Qwen после рубрики | Ornith после рубрики | Wall всех 4, Qwen/Ornith |
|---|---:|---:|---:|
| Русский/рассуждения | 3/4 | 1/4 | 628.71/333.01 с |
| Coding, завершённые сценарии | 1/4 | 0/4 | 580.95/1115.77 с |
| Agentic | 3/4 | 2/4 | 154.65/338.36 с |

Скрытые assertions Ornith: C1/C2/C4 FAIL, C3 PASS при незавершённом budgetсценарии. A3 service assertions PASS, model endpoint+process verification не завершена. A2 --version реально вернул exactversion+fixture-build-17 и непосредственно captured exit0 в trusted rawexec, но frozen recognizer их не распознал в составномshell; primary6turn BUDGET сохраняется.

Wall блока включает все ошибки; это стоимость workload, а не сравнение скорости правильных ответов.

Совпавшие успешные задачи (3/12): R1, A1, A4. Сумма их taskwall Qwen 163.39 с / Ornith 154.64 с. Без известных cacheeligible исходных выполнений: R1, A1, A4 — 163.39/154.64 с. Qwen C1 — infrastructure rerun/cacheeligible; прямой uncached вывод по нему ограничен. Быстрые неуспехи остаются в общей таблице.

Время совпавших успешных по блокам: русский R1 — Qwen 96.37 / Ornith 38.55 с; coding — общих завершённых PASS нет; tools A1+A4 — Qwen 67.03 / Ornith 116.09 с (Ornith медленнее). Общая сумма трёх после prose-рубрики смешивает эти разнонаправленные эффекты. Frozen CLI отдельно сравнивает только два машинных PASS: A1/A4.

Длинный R4: Qwen 242.25 с / Ornith 145.82 с; одинаковый текст, prompt_tokens26309/26271. Configured context обоих 262144; весь этот максимум данный набор не проверяет.

Ornith в R4 верно понял все шесть актуальных значений и отмены (prose2/2), но нарушил схему evidence и требование unknown→[]; это строгий контрактFAIL. R2 нарушил заголовок и сделал чрезмерный причинный вывод; R3 вернул пустой final при finish=stop; причина MODEL_OR_RUNTIME_PARSER_UNRESOLVED. Эти провалы не исправлялись по ответам.

| Повторный якорь | Qwen | Ornith |
|---|---|---|
| R3 REPEAT/CACHE-ELIGIBLE | PASS; 13.62 с | PASS; 14.24 с |
| C1 REPEAT/CACHE-ELIGIBLE | PASS; 156.28 с | BUDGET_EXHAUSTED; 249.53 с |
| A2 REPEAT/CACHE-ELIGIBLE | PASS; 40.58 с | BUDGET_EXHAUSTED; 57.92 с |

FALSE_SUCCESS среди 12: Qwen 0, Ornith 0; LOOP: Qwen 0, Ornith 0. Budget-exhausted reasoning не объявляется LOOP.

Ошибки основных 12 (machine): Qwen{"PARTIAL": 3, "PASS": 5, "BUDGET_EXHAUSTED": 3, "TOOL_ERROR": 1}; Ornith{"PARTIAL": 1, "WRONG_RESULT": 3, "BUDGET_EXHAUSTED": 6, "PASS": 2}. FALSE_SUCCESS/LOOP выводится консервативным замороженным классификатором; ноль не доказывает абсолютную стабильность. Anchors не добавляют три уникальных успеха.

Это сравнение полезных deployments: разные weights/tokenizers/runtime/speculation/samplers и resident memory (Qwen baseline содержал embeddings4B, Ornith без embeddings), при одном frozen suite,runner и бюджетах. Qwen исторически имел раскрытые compatfix и один affectedC1rerun; здесь используется его canonical derived final view. Продуктовый маршрут не переключался. P95, статистическая значимость и универсальное превосходство не заявляются. На этом срезе убедительного обновления общего endpoint нет: сохранять Qwen для общей работы. Ornith быстрее в отдельных русских ответах, но уступает по строгому выполнению и завершению coding; его рабочий endpoint остаётся экспериментальным. Follow-on tuning/rerun не выполнялось.

Замер Ornith: 24.10.2026, 01:00:47–01:35:57 МСК. Один посторонний прогрев 0.754 с, затем15 сценариев/51 вызов; прогрев в score не включён. Финальное здоровье проверено01:36:09, свои процессы и слот освобождены01:36:45. Все52 запроса и15sandbox подтверждённо очищены. Задание исполнителя с подготовкой/очисткой заняло39мин17с. Проверены55 замороженных файлов; исходные prompts иtool-схемы совпали во всех15 парах.

Локальные квоты runner в исходной диагностике определены неполно: отсутствие файлов cpu.max/memory.max в корне cgroup2 ошибочно названо v1. Позднее Астра прочла фактическую v2-иерархию и всех предков; это не доказывает неизменность квот на всём интервале. Пиковые и непрерывные ресурсные наблюдения отсутствуют; локальная продуктовая Python/IO работа была раскрыта.

Контрольные SHA-256 исходных материалов: frozen suite `887ba6f21336ee5294f98666f8e322c3263c2c517e82bfcc4d3288336a0294f9`; final Ornith run `a29efb1c861226f7381c2878234f4b2d513f4b74c2892a33343f97a3f84b1fff`; итоговая независимая сверка `6ed96009dbddda72f5f1837933856735b5b76cb3131a1d305e9af7e242390bd5`. Исторические Qwen/Ornith raw и отчёты сохранены отдельно; публикация содержит только результаты и границы вывода, без приватных трасс и данных.
