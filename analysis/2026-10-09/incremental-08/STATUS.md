# Статус среза

| Слой | Фактический результат |
|---|---|
| Объединённый исходник | Подготовлен; exact manifest 3e337e50 |
| Независимое source review | J1/R1/R2 закрыты; eligible for bounded build |
| Compiler build | Две первые DSO PASS; hashes 3223a686 / 39c0dfdd |
| ELF | Статические данные прочитаны; libc.so.6, без RPATH/RUNPATH; Python API ожидает загрузку в выбранный interpreter |
| Source wiring | Связано в коде; runtime не выполнен |
| ABI/provider/kernel/F6 | NOT_RUN / UNACCEPTED |
| Установленный продукт, 7 journeys / 4 web | UNACCEPTED |
| Публикация | Подготовка требует независимого root review |

180/45/root6, AS2GiB, CPU0,1, GNU60+полные60 closure, все11 режимов, 277/831, 38/114, paired512, deny125 и foreign-thread сохранены. Старый продукт OFF. Новые runtime grants, перезапуски consumed G20 и перенос старого PASS на новые байты отсутствуют.
