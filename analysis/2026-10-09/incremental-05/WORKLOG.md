# Журнал выбранного среза, 09.10.2026 (МСК)

| Автор / пакет | Что изменилось и зачем | Время исходного пакета | Фактический статус |
|---|---|---|---|
| Astra: request identity | Разделены immutable returned bytes, mutable graph и worker request/completion identity | 18:32:59–18:56:03, 1384.592с | Source prepared; review18:58:40–19:09:16 выявило два новых source-блокера |
| Sol: cache identity | Входящий fetch отделён от повторного использования уже выполненного module/promise; полный shared-worker-chain сохранён, всего22 negatives | Принято19:17:54; source19:38:34; pre-R1 19:40:09. Итог CLOSED1395.337883с/1800 | Cache/VM source принят; selector defect исправлен Астрой19:56:48; r2-review19:58:49 принимает source-композицию (852.569567с/1200). Wiring отсутствует, current controls NOT_RUN |
| Sol: finite callback owner | Root6 и реальные GNU/mode credits, subreaper/wait4; original GNU60+closure60 | 18:36:17–18:59:03 result1366.444с; final closure18:59:45, 1408.681635с/1800 | Source F5 blocked; review подтверждает F1/F2/F3 и сохраняет F4/F5/F6 |
| Astra: custody successor | Persistent reap state; отдельная proven custody; отказ от killpg после утраты authority; hard-limit reservation до fork; частичный caller join | Принято19:25:49; окончено19:44:00. Консервативный original1144.685658с/1800, с принятия1090.798472с | Source repairs заявлены автором, независимое review pending; F4/F5/F6 остаются |
| Astra: ptrace proposal/review | Source-проверка inherited attach/EXITKILL и GNU signal delivery; найден конфликт permanent tracing с GNU60 | Source proposal19:35:38; review566.015093с/900 | Kernel mechanism supported; timer-ready/detach bootstrap не реализован; ptrace NOT_RUN |
| Astra: публикационная сверка | 51 PEER:45 прямых public summary; ещё2 ранее опубликованных result найдены по содержимому; diagnostic wrapper/status восстановлены;2 новых result добавлены;1 pause сохранена | Срез peer19:41:47; эта подготовка принята19:51:00 | Частичный source/process-пакет, не полнота суток и не релиз |

Source/seal/send/closure времена — вложенные отметки одного исходного бюджета, не суммируемые отдельные задания. Полные точные времена, причины отказов и исходные SHA сохранены в outcomes.json; сводные числа округлены только в этой таблице.

Следующее недостающее доказательство: независимое review callback source, привязка принятой TS source-композиции в будущие manifest/control maps, конкретная допустимая caller/native boundary и GNU bootstrap; затем реальные неизменные положительные и отрицательные контроли, kernel timing/CPU/identity/custody, полные обязательные gates. Статический код или prepared control не заменяет это выполнение. Новые активные работы не включены как завершённые.
