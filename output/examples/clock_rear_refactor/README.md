# Три корпуса часов: задние саморезы

Редакция от 18.11.2026, отдельная от исторических clock_family/clock_module.
Зависит от PR #2; main, PR #2 и инженерные паттерны PR #4 этим выпуском не сливаются.

- [Сборки спереди](assembled.png), [сзади](rear.png), [с разнесёнными деталями](exploded.png).
- [PDF сборок](assembled.pdf), [задних крышек](rear.pdf), [деталей](exploded.pdf).
- [Габаритный чертёж покупного модуля](module-drawing.pdf).
- [STEP/STL, исходники и доказательства](clock-rear-refactor.zip).
- [Приёмка и SHA-256 поставки](acceptance.json).

Все три корпуса имеют крышки на четырёх саморезах EJOT DELTA PT 30×12
WN5452 (арт. 4230714809, привод 10IP), вводимых сзади. На фасаде крепёжных
проходов нет. У portable ушко объединено с корпусом и доведено до задней
плоскости крышки; крышка снимается отдельно. У wall подвес скрыт в крышке:
перед открыванием часы снимаются со стеновых головок.

Подвес рассчитан геометрически для контрольного деревянного щита 30 мм
и двух Würth ASSY4 PH 4×25 (0153740025, RW20). Реальная стена и анкеры
этим выбором не аттестованы. Размеры и источники приведены в
[контракте](../../../models/clock_family/REFACTOR.md).

Для печати предназначены только body/lid STL и два pilot-coupon STL.
Сборочные STEP содержат покупные детали. Резьба и приводы показаны габаритами.
Купон позволяет проверить пилоты 2.3/2.4/2.5 мм до печати полного корпуса.
Физические посадка PETG, затяжка, срыв и ресурс саморезов, OEM-кольцо,
обслуживание реального модуля, нагрузки и анкеры остаются NOT_CHECKED.

Проверки: геометрия до/после импорта STEP, STL, отсутствие крепёжных
проходов на фасаде, опоры/пилоты/головки, запас до дна, доступ отвёртки,
пути снятия крышек и подвеса, заднее ушко. За пределами разрешённых зон
изменения относительно четырёх опубликованных исторических STEP — 0 мм³.
Опыт припуска 0.4→1.0 сохраняет крышки и фурнитуру; намеренные дефекты
отвергаются. Итоговые числа и независимое ревью — в acceptance.json.

## Точная область хэшей

`acceptance.json` содержит две таблицы: `delivery_source_sha256` и
`delivery_artifact_sha256`. Они проверяют **сырые Git blobs одного commit**:
никакой нормализации LF/CRLF. Сам acceptance.json исключён во избежание
самоссылки; локальный output вне перечисленных путей не входит в поставку.
Commit выбирается явно, например точный SHA опубликованной ветки PR.

Внутри ZIP `release-manifest.json` связывает каждый другой член по его
точным байтам, включая снимки runtime-источников, отчёты и результаты опыта.
Хэши источников внутри CAD-отчётов относятся именно к этим runtime-байтам.
Они могут отличаться от LF Git и не переименовываются в хэши поставки.
Исторический архив и его входы сохранены неизменными.

Из корня клона стандартным Python:

```python
import hashlib, io, json, subprocess, zipfile

commit = "origin/work/clock-rear-fasteners"  # сначала git fetch; можно точный SHA
commit = subprocess.check_output([
    "git", "rev-parse", "--verify", "--end-of-options", f"{commit}^{{commit}}"
]).decode().strip()
def blob(path):
    return subprocess.check_output(["git", "show", f"{commit}:{path}"])
def sha(data):
    return hashlib.sha256(data).hexdigest()
base = "output/examples/clock_rear_refactor/"
a = json.loads(blob(base + "acceptance.json"))
for field in ("delivery_source_sha256", "delivery_artifact_sha256"):
    for path, expected in a[field].items():
        assert sha(blob(path)) == expected, path
with zipfile.ZipFile(io.BytesIO(blob(base + "clock-rear-refactor.zip"))) as z:
    m = json.loads(z.read("release-manifest.json"))
    assert set(z.namelist()) == set(m["sha256"]) | {"release-manifest.json"}
    for path, expected in m["sha256"].items():
        assert sha(z.read(path)) == expected, path
print("Delivery and exact runtime ZIP bytes: PASS")
```

Воспроизведение CAD — по [README модели](../../../models/clock_family/README.md).
