# Evidence независимого переноса

[Контекст и границы изоляции](context.md), [точная задача](pilot-prompt.txt),
[переданные файлы](pilot-input.zip), [их SHA](pilot-input-sha256.json),
[происхождение](input-provenance.json).

Наблюдаемое поведение: [отчёт агента](review.md),
[фактически прочитанные входы](read-inputs.json),
[код измерений](measure.py), [актуальный результат](measurements.json),
[техническая ошибка и последовательные запуски](execution-notes.txt).
[Первоначальный JSON](before-argv.json) относится к версии до добавления argv;
его старый scriptSHA не приписывается опубликованной новой версии скрипта.
Геометрические поля обоих JSON сверены и полностью совпали.

Повтор из checkout этой ветки. Полезные команды выполняются внутри общего
managed Windows executor с owner `heavy:filter-review`, timeout120:

```powershell
Expand-Archive -LiteralPath docs/engineering-review/evidence/pilot-input.zip -DestinationPath output/engineering-review/replay-input
.venv/Scripts/python.exe -B docs/engineering-review/evidence/measure.py output/engineering-review/replay-input --output-dir output/engineering-review/replay-result
```

Не используй уже занятый каталог назначения. Повтор измерений воспроизводит
численный результат; для повтора поведения агента создай свежий контекст и дай
ему [задачу](pilot-prompt.txt) с актуальными путями, без исходного review или
оценочного validator. Исторический контекст и результаты не выдаются за вход
нового слепого испытания.

[Регрессия pytest](regression.json) относится к отдельной ветке от main:
115 passed, 0 failures/errors/skips. Код выхода0 и завершение дерева получены
в managed executor. Физическое одобрение изделия этим не заявляется.
