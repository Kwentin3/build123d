# build123d CAD Lab / Agent Skills

Небольшая CAD-лаборатория: редактируемые параметрические модели на Python и пять
нативных Agent Skills для работы с ними. Можно строить детали и сборки, измерять
геометрию, проверять пересечения и последовательность разборки, выпускать STEP,
STL, плоские DXF, спецификации и документы — в пределах возможностей выбранной модели.

Стек: [build123d](https://github.com/gumyr/build123d), Open Cascade через OCP,
pytest и необязательный OCP CAD Viewer для VS Code. Расчёт клинового узла использует
NumPy/SciPy. Skills направляют работу агента; инструменты — существующие Python CLI.
Отдельного агентного фреймворка, MCP и проектного сервера нет.
Для ручного запуска моделей агент и Skills не требуются.

## Что находится в репозитории

```text
models/
  plate/          # пластина 100 × 60 × 8 мм, отверстие Ø12 мм
  gear/           # эксперимент с эвольвентной шестернёй
  mangal/         # исходный разборный мангал
  mangal_wedge/   # исследование механики клинового узла
  mangal_v2/      # следующая конструкция, выпуск 2.0
  mangal_v21/     # выпуск 2.1: пять деталей, без чек
tests/            # тесты пластины; остальные тесты лежат рядом с моделями
.agents/skills/   # cad-entry, cad-modeling, cad-validation,
                  # cad-assembly, cad-manufacturing
.vscode/          # рекомендации расширений, интерпретатор и F5
output/examples/  # опубликованные исторические демонстрационные материалы
requirements.txt  # точные версии общего Python-окружения
```

Все модели сохранены. Семейство мангала развивается последовательно:
2.1 повторно использует код 2.0, исходного мангала и исследования механики.
Для запуска сохраняй дерево `models/` целиком. Требования и ограничения изделия
описаны в его README: [пластина](#первый-запуск), [шестерня](models/gear/README.md),
[мангал](models/mangal/README.md), [клин](models/mangal_wedge/README.md),
[2.0](models/mangal_v2/README.md), [2.1](models/mangal_v21/README.md).

[Примеры](output/examples/README.md) содержат датированные PDF/PNG и переносимые
`example-report.json` для пластины и мангала 2.1. Это исторические демонстрации,
а не свежая приёмка твоего окружения. Обычные результаты `output/<name>/`,
локальные evidence, `.venv/` и кэши в Git не включены.

[Engineering Review Patterns](docs/engineering-review/README.md) связывает
проверки с назначением крепления, сопряжения и обслуживания. Это дополнение
существующих пяти Skills; [учебный держатель фильтра](models/filter_holder/README.md)
служит независимым контрольным примером, не производственным изделием.

## Установка на Windows

Проверенная среда проекта — Windows x64, Python 3.13.7.
Установи Python 3.13 x64 с [python.org](https://www.python.org/downloads/windows/),
склонируй репозиторий и открой PowerShell в его корне. Затем:

```powershell
git clone https://github.com/Kwentin3/build123d.git
cd build123d
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --index-url https://pypi.org/simple -r requirements.txt
.\.venv\Scripts\python.exe --version
.\.venv\Scripts\python.exe -m pip check
```

`requirements.txt` фиксирует существующее окружение вместе с транзитивными
зависимостями. Не меняй версии только ради повторного запуска.
Активация окружения и изменение ExecutionPolicy не нужны.
Установка и приёмка на Linux/VPS в этом проекте не проверены.

## Первый запуск

Из корня репозитория, без просмотрщика:

```powershell
.\.venv\Scripts\python.exe models/plate/model.py
.\.venv\Scripts\python.exe models/mangal/model.py
.\.venv\Scripts\python.exe models/mangal_v21/model.py
.\.venv\Scripts\python.exe -m pytest -q
```

Будут созданы `output/plate/`, `output/mangal/` и `output/mangal_v21/`.
У пластины — STEP/STL и отчёт; у мангала — сборка STEP, плоские DXF,
спецификация и документы. Открой свежие `report.json` и сопоставь измерения
с заданием: одного кода выхода 0 для приёмки недостаточно.

**Полный pytest можно запускать сразу на чистом клоне.** Его fixture сама
построит исходный мангал во временном каталоге. Для ручного исследования
`mangal_wedge` сначала нужен свежий исходный мангал: исследование проверяет
SHA его исходников, потребляемого BOM и согласованность измерений отчёта.
Устаревшие входы дают технический отказ, а не новый расчёт. Запуск:

```powershell
.\.venv\Scripts\python.exe models/mangal_wedge/model.py
```

Другой каталог входов передаётся через `--reference-dir`; результаты — через
`--output-dir`. Ранее оставшиеся CSV/SVG после отказа не считаются текущими.

Его `design_requirements_status=FAIL` намеренно фиксирует найденное противоречие
требований. Это исследовательский пример, не основной демонстрационный запуск;
успешное выполнение расчёта не означает пригодность узла.

## Изменение параметров и отдельный результат

Размеры заданы в миллиметрах именованными параметрами в начале `model.py`
или полями `Params`. Доступные аргументы смотри через `--help`.
CLI-параметр меняет текущий запуск, а не исходный файл. Например:

```powershell
.\.venv\Scripts\python.exe models/plate/model.py --width 120 --output-dir output/plate/variant_120
.\.venv\Scripts\python.exe models/mangal_v21/model.py --thickness 4 --output-dir output/mangal_v21/variant_4mm
```

У каждого результата должен быть один писатель. Для эксперимента используй
отдельный каталог; не перезаписывай принятый выпуск и не меняй исходники во время
построения. Новый вариант требует собственных измерений и проверок.

Для локальной правки сначала сохрани принятую геометрию, укажи разрешённый
признак и защищённые детали. `check_bore_change` пластины и `check_guide_change`
мангала 2.1 сравнивают тела штатными Boolean-операциями; они дополняют измерения
и STEP roundtrip. [Короткая инструкция и Python API](.agents/skills/cad-validation/references/local-edits.md)
объясняет границы этих двух проверок и выбор затронутых тестов.

## Просмотр, снимки и PDF

Для численных проверок и экспорта окно viewer не требуется.
Для просмотра установи VS Code и рекомендованные в `.vscode/extensions.json`
расширения Python и OCP CAD Viewer:

```powershell
code --install-extension ms-python.python
code --install-extension bernhard-42.ocp-cad-viewer@4.2.0
```

Открой проект в VS Code, выбери `.venv/Scripts/python.exe` через
`Python: Select Interpreter` и выполни `OCP CAD Viewer: Open viewer`.
После установки расширений при необходимости выполни `Developer: Reload Window`.
Существующие конфигурации F5 показывают пластину и шестерню.

```powershell
.\.venv\Scripts\python.exe models/plate/model.py --show
.\.venv\Scripts\python.exe models/plate/model.py --screenshots
.\.venv\Scripts\python.exe models/mangal_v21/model.py --screenshots
.\.venv\Scripts\python.exe models/mangal_v21/documentation.py
```

PDF использует установленный Chrome; его путь можно передать аргументом
`--browser "C:\Program Files\Google\Chrome\Application\chrome.exe"`.
Документ 2.1 требует свежие снимки, связанные с текущим отчётом.
Открой полученные PNG и PDF перед визуальными выводами.
Снимок подтверждает внешний вид, численные размеры проверяет валидатор.
При недоступном viewer запрошенные снимки могут завершиться технической ошибкой.

## Работа с агентом

Codex использует нативный каталог `.agents/skills/`. Начни обычным CAD-запросом
или явно вызови `$cad-entry`. Например: «Измени ширину пластины на 120 мм,
сохрани отдельный результат и проверь размеры и STEP после импорта».
Если Skills не появились после добавления репозитория, перезапусти сеанс.
Другому host нужен его штатный механизм Agent Skills; прямое чтение
`.agents/skills/cad-entry/SKILL.md` — запасной путь.

Для локальной правки достаточно cad-entry → cad-modeling + cad-validation.
cad-assembly нужен для сборок и траекторий, cad-manufacturing — для выпуска
под выбранный процесс. Порядок работы и обычной передачи задачи другому агенту
описан в [WORKFLOW.md](WORKFLOW.md): цель, исходники, границы, результат и приёмка.
Держи требования в README модели или существующей записи задачи.

## Проверка и продолжение работы

После изменения запусти затронутую модель, её проверки и полный `pytest`.
В отчёте различай `PASS`, инженерный `FAIL`, техническую ошибку и
`NOT_CHECKED` с причиной. Проверяй измеренное против требуемого и результат
повторного импорта STEP. Геометрический PASS не заменяет физических испытаний.

При возобновлении прочитай README модели, задание и Git diff. Сверь хэши отчёта
с текущими файлами: пластина и 2.1 записывают источники, зависимости и артефакты.
Пример для текущего отчёта 2.1 — обычный Python-код из корня проекта:

```python
import hashlib, json
from pathlib import Path

root = Path.cwd()
model, out = root / "models/mangal_v21", root / "output/mangal_v21"
r = json.loads((out / "report.json").read_text(encoding="utf-8"))
for base, hashes in ((model, r["source_sha256"]),
                     (root, r["dependency_source_sha256"]),
                     (out, r["artifacts"]["sha256"])):
    assert hashes, "Нет привязки: повторить запуск"
    for name, expected in hashes.items():
        assert hashlib.sha256((base / name).read_bytes()).hexdigest() == expected, name
```

Нет привязки или изменился вход — повтори соответствующий запуск.
Совпадение хэшей доказывает соответствие файлов, затем нужно оценить содержание
отчёта. Хэш requirements не проверяет установленное окружение: используй версии
Python/пакетов и `pip check`. После новых снимков повтори визуальную проверку.

## Новая модель

Создай `models/<name>/model.py` с параметрами в начале и CLI под
`if __name__ == "__main__":`. Результаты направляй в `output/<name>/`,
тесты добавляй рядом с моделью или в `tests/`; запускай через `python -m pytest`.
Используй штатные API build123d/OCP и существующее окружение.
Для STL на Windows сохрани приём `contextlib.chdir` из пластины:
экспорт в каталоге назначения по ASCII-имени обходит проблему кириллических путей.
Добавляй проверки конкретных требований и STEP после повторного импорта.

Подробнее: [ARCHITECTURE.md](ARCHITECTURE.md) — границы и переносимость;
[WORKFLOW.md](WORKFLOW.md) — процесс; [AUDIT.md](AUDIT.md) — источники и приёмка;
[GOAL.md](GOAL.md) — текущая работа, не реестр моделей.
