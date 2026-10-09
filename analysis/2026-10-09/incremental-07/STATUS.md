Обе реализации не приняты. Три валидных source findings R1/R2/J1 требуют исправления на отдельном объединённом candidate. Принятие результатов review подтверждает дефекты и не означает приёмку кода.

| Уровень | F4 native | F5 bootstrap |
| --- | --- | --- |
| Исходники | Все шесть authored files сохранены | GNU shim/map/TraceCustody и изменённые source bodies сохранены |
| Подключение | Source overlay в существующий caller; hard refusal сохранён | Owner/launcher/mode связаны в источнике; финального F4 join нет |
| Offline | 5 AST; C syntax exit0; independent source review | 231 авторская static проверка, 21 AST; C syntax exit0; root source review |
| Найденные отказы | R1 gate после CPU/kill failure; R2 пропуск custody recovery | J1: 3 stale references из 76 |
| Final build / ABI | NOT_RUN | NOT_RUN |
| Live / F6 | NOT_RUN | NOT_RUN |
| Release acceptance | UNACCEPTED | UNACCEPTED |

Оригинальные ограничения и полный scope сохранены в [prepared-controls.json](prepared-controls.json). Все 7 journeys / 4 web — UNACCEPTED; прежняя Friday OFF; G20 FAILED137, CONSUMED/CLOSED, без retry. Продукт не изменён. Активный join/repair и F6 preparation исключены из среза.
