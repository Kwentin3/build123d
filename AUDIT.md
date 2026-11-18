# Аудит CAD Harness · 18 ноября 2026

## Что было

Шесть каталогов моделей: plate, gear, mangal, mangal_wedge, mangal_v2,
mangal_v21. Последние четыре — история разработки изделия, не четыре
независимых универсальных компонента. Общие `.venv` и pinned requirements;
генерация, валидация, экспорт и отчётность уже реализованы.

| Компонент | Наблюдение и решение |
| --- | --- |
| Plate | `make_plate`/`run_plate`; отдельный `validation.py` измеряет отверстие, толщину, объём и STEP. Оставить владельцем требований пластины |
| Gear | Собственные профиль, валидатор и тесты; не превращать в универсальную проверку зубчатых передач |
| Сборки | `models/mangal/validation.py`: пересечения и sweep поступательного движения для поддержанных поверхностей; v21 учитывает последовательное изменение поз |
| Экспорт | Native STEP/STL, ezdxf, SVG/BOM/Markdown; сохранить Unicode workaround через cwd/ASCII basename |
| Viewer | Существующий OCP CAD Viewer, камеры и `--screenshots`; PNG нужно открыть отдельно |
| Документы | Модельные генераторы PDF/HTML и проверки хэшей; это существующие возможности, не новый слой Harness |
| Дублирование | Plate/gear повторяют несколько стадий runner/viewer; вынос сейчас не окупает изменение работающего runtime |
| VS Code / pytest | Интерпретатор/F5 уже настроены; discovery использует единый штатный `pytest.ini`: `tests` и `models`, без архивов запусков в `output` |
| Состояние | `report.json` — последний запуск, а не история; Git изначально отсутствовал |

Локальный baseline `f0e4a1f81d7f2a4a93be5c4f2587ecc2c64e47e9` сохраняет
исходный CAD Lab. Существующие модели и output дополнительно зафиксированы
в `output/harness/baseline-sha256.json`. В output ничего не следует считать
текущим только по дате файла или прежнему PASS.

## Исследование первоисточников

Официальные механизмы:

- [build123d import/export](https://build123d.readthedocs.io/en/latest/import_export.html),
  [native exporters](https://github.com/gumyr/build123d/blob/dev/src/build123d/exporters3d.py):
  использовать штатный Python API; `latest/dev` сверять с установленной 0.13.0.
- [Agent Skills specification](https://agentskills.io/specification):
  имя/описание → SKILL.md → условные references. Необходим только SKILL.md.
- [Нативные Skills Codex](https://learn.chatgpt.com/docs/build-skills):
  repo discovery из `.agents/skills`, implicit/explicit invocation; каталог
  имеет бюджет контекста и может сокращаться при большом числе навыков.

Опыт сообщества, проверенный по реализации, а не только README:

| Проект | Что установлено по коду и что применено здесь |
| --- | --- |
| [build123d-mcp worker](https://github.com/pzfreo/build123d-mcp/blob/main/src/build123d_mcp/worker.py), [server](https://github.com/pzfreo/build123d-mcp/blob/main/src/build123d_mcp/server.py) | Stateful worker и `execute_file` с хэшем исходника. Применена идея source-backed CAD; постоянная session/MCP не нужна |
| [cad-agent runner](https://github.com/Agincourt-Systems/cad-agent/blob/master/src/cadx/runner.py), [constraints](https://github.com/Agincourt-Systems/cad-agent/blob/master/pyproject.toml) | Run directories, параметры, diagnostics; ограничение версии build123d относится к его маршрутам interference/render. Используем существующий отчёт, не переносим registry/DSL/loop |
| [text-to-cad skill](https://github.com/earthtojake/text-to-cad/blob/main/skills/cad/SKILL.md), [runtime constraints](https://github.com/earthtojake/text-to-cad/blob/main/packages/cad/pyproject.toml) | Полезны условные references. Runtime вмешивается во внутренние API build123d; для этого пилота не подходит |
| [claudecad verification](https://github.com/mdbritt/claudecad/blob/main/claudecad/verify.py), [export](https://github.com/mdbritt/claudecad/blob/main/claudecad/export.py) | Численные и визуальные проверки разделены; сам exporter не является универсальным acceptance gate. Применено разделение свидетельств |
| [build123d-cad skill](https://github.com/wngfra/build123d-cad/blob/main/SKILL.md), [validator](https://github.com/wngfra/build123d-cad/blob/main/scripts/cad_validate.py) | Подходящий малый масштаб. Bounds-based clearance и обработка исключений не дают достаточного инженерного доказательства; валидатор не заимствован |

Разобранные ограничения и обсуждения:

- [gumyr discussion 1231](https://github.com/gumyr/build123d/discussions/1231):
  сохранять редактируемый результат LLM; [1537](https://github.com/gumyr/build123d/discussions/1537):
  размерные тесты могут пропустить несвязные тела.
- [STEP labels 1548](https://github.com/gumyr/build123d/issues/1548):
  геометрический round trip и сохранность метаданных — разные проверки.
- [MCP shared state 438](https://github.com/pzfreo/build123d-mcp/issues/438):
  общая `current_shape` конфликтует между агентами. Наши проекты сохраняют свои файлы.
- [MCP 443](https://github.com/pzfreo/build123d-mcp/issues/443): открытая задача
  не означает отсутствия `execute_file` в текущем source; исходник уже содержит его.
- [MCP 461](https://github.com/pzfreo/build123d-mcp/issues/461),
  [462](https://github.com/pzfreo/build123d-mcp/issues/462),
  [text-to-cad 703](https://github.com/earthtojake/text-to-cad/issues/703):
  валидность/объём/тесселяция не заменяют проверку требуемой геометрии.
- [text-to-cad 822](https://github.com/earthtojake/text-to-cad/issues/822):
  workaround должен иметь точную область и критерий удаления.

Для cad-agent, claudecad и wngfra в проверенных открытых списках issues
обсуждений не обнаружено; это не показатель зрелости. Сторонний исполняемый
код не копировался и не устанавливался. Ссылки на ветки отражают просмотренное
состояние на дату аудита, а не неизменяемые релизы.

Наше архитектурное решение: сохранить владельцев модели/проверок/экспорта,
добавить только Skills, workflow и небольшие исправления текущих manifests.
Это предложение проекта, а не обязательная рекомендация авторов библиотек.

## Приёмка и остаток

Нативное обнаружение: после создания файлов все пять CAD Skills появились
в каталоге текущего Codex IDE-сеанса, затем в свежем агентном контексте
испытателя пластины. Тела навыков не помещены в AGENTS.md.

| Испытание | Наблюдаемый результат |
| --- | --- |
| Правка пластины | В копии изменён исходный WIDTH на 110; получены 110×60×8 мм, Ø12, объём 51895.221316 мм³ и успешный STEP round trip |
| Ошибка/восстановление | Отверстие смещено на +10 мм X при прежнем требовании. Старый PASS отвергнут по хэшу до запуска; затем engineering FAIL/1 по положению/оси и STEP. Возврат правильного исходника сохранил WIDTH110 и дал PASS/0 |
| Сборка | В памяти проверено предложение guide_up_allowance 0,7→0,8 мм: оба варианта 28/28 PASS, четыре последовательных continuous translation sweep, прежние габариты/лист/число деталей сохранены. Утверждённая конструкция не менялась |
| Текущие native CLI | Plate: 21 PASS/5 NOT_CHECKED; v21: 35 PASS/7 NOT_CHECKED, geometry/execution PASS. STEP импортирован и проверен обоими генераторами |
| Актуальность | 27 source/dependency/artifact-привязок текущих двух отчётов совпали с реальными файлами; прежние output не изменились по baseline |

Локальные evidence: `output/harness/plate-scenarios/README.md`,
`output/harness/scenario2.json`, `output/harness/plate/report.json`,
`output/harness/mangal_v21/report.json`. Это локальные generated artifacts,
исключённые из Git, а не часть runtime. Архив пластины сохраняет исходники,
отчёты и точные STEP/STL каждой стадии; 23 сохранённых файла сверены по хэшам.

Lazy loading: свежий испытатель пластины прочитал cad-entry, cad-modeling,
cad-validation и необходимые исходники/README; cad-assembly,
cad-manufacturing, laser-cutting reference и полный WORKFLOW не читались.
Для сборки прочитаны entry/assembly/validation; остальные specialties не нужны.
Сборочный сценарий выполнен в продолженном исследовательском контексте,
а не в отдельном чистом сеансе. Численные измерения получены инструментами.
Достоверных метрик provider tokens/полного переданного контекста нет;
на уровне доступного каталога и журналов чтения обнаружение и выбор подтверждены.
Время сборочного сравнения — 14,96 с; финальные 12 тестов пластины в копии — 35,53 с.

Найдены и исправлены два наблюдаемых дефекта, помимо привязки отчётов:
отрицательный тест пластины неявно зависел от WIDTH100 (теперь явно задаёт
width=100, сохраняя ожидание 120); общий pytest собирал тестовые копии из output
(исправлено штатным testpaths). Первичная ошибка collection сохранена в
`output/harness/pytest-collection-error.xml`; это не инженерный FAIL модели.
Полный повторный `.venv/Scripts/python.exe -m pytest -q` с дополнительным
`--junitxml=output/harness/pytest.xml`: **70 passed за 337,27 с**, код 0.
Новых зависимостей нет; `pip check` успешен. Все пять Skills прошли штатный
quick_validate (существующий системный Python; в CAD venv нет PyYAML).
Для проверки самого CAD и всех тестов использовался проектный Python 3.13.7:
build123d 0.13.0, cadquery-ocp-novtk 8.0.1.1.0, ocp_vscode 4.2.0, pytest 9.2.0.

Временная рабочая копия и сгенерированные диагностические схемы удалены;
результаты контрольных испытаний сохранены отдельно. Новых screenshots/PDF
в этом этапе не выпускали; физические/viewer-пункты NOT_CHECKED имеют
соответствующие причины в свежих отчётах.

112 прежних output-файлов сохранились без изменений; из 144 baseline-файлов
изменились только четыре согласованных модельных/тестовых исходника.
Сводка сохранности: локальный `output/harness/preservation.json`. Текущая геометрия
сохранена; отличие runner — только учёт evidence, документации — запрет
непривязанных старых снимков. Полнота raw provider context и физические
свойства этим этапом не аттестуются.

Независимая приёмка: **PASS**. Reviewer самостоятельно проверил manifests,
архивные и текущие отчёты, JUnit, сохранность файлов и соответствие документов;
нарушений согласованного объёма и KISS/native-ограничений не обнаружил.

Ограничения: физические свойства и Hermes/Linux не проверены; безопасная
многопользовательская серверная среда остаётся будущей работой. Требования
к ней перечислены в ARCHITECTURE.md. Новый checker/runner после уточнения
пользователя отменён до реализации. Основные CLI и геометрия сохраняются.

## Передача отдельной работы

На опоре `88143cd` уточнён только раздел WORKFLOW.md и вход cad-entry:
задание с достаточными входами/зависимостями, границами и проверяемым возвратом.
Обычного сообщения достаточно; отдельный brief не обязателен. Используются
штатные subagents, Skills и файлы. Новый runtime/диспетчер/формат состояния
не создавался. Предметные условия опыта в общий workflow не переносились.
Решение соответствует рассмотренным [task briefs Superpowers](https://github.com/obra/superpowers/blob/main/skills/subagent-driven-development/SKILL.md)
и [различию isolated/fork у LangChain](https://www.langchain.com/blog/organizing-context-in-a-multi-agent-harness);
чужой исполняемый код не заимствовался.

Один новый исполнитель, вызванный с `fork_turns="none"`, получил сохранённое
локальное задание `output/handoff/brief.md` на уже известный вариант направляющей мангала
0,7→0,8 мм. Без изменения исходников проверены сопрягаемые детали, четыре
последовательных движения и STEP. Только торцы имеют геометрическую разность;
стенки и дно прежние. Native report: 35 PASS/7 NOT_CHECKED. Единственный полный
pytest: **70 passed за 313,18 с**, exit 0. CAD-опыт занял 14,110 с.
Основной агент сверил результат с заданием; это исследованный вариант,
не принятие новой конструкции. Физическая приёмка остаётся NOT_CHECKED.

Локальные `output/handoff/report.md`, `output/handoff/dispatch.md`,
`output/handoff/variant/comparison.json`, `output/handoff/variant/pytest.log`
сохранены как локальные evidence, исключённые из Git. Существенных запросов
недостающих данных не было. Прочитаны entry/modeling/assembly/validation,
связанные исходники, правила записи отчёта и исполнения; выполнен поиск
memory-указателя без чтения rollout. История обсуждения вызовом не передавалась,
но среда содержала общие инструкции, Skills/tools и memory summary.
Полный вход провайдера и точные tokens не наблюдались; сравнительного запуска
нет. Поэтому применимость показана только для этого примера; экономия,
причина успеха и универсальность не утверждаются.

Независимое чтение нового общего раздела не выявило предметных правил,
обязательного шаблона или причинного обобщения. Все 112 прежних output
сохранены; модели и тесты относительно опоры не изменены. Временные каталоги
pytest удалены адресно, процесс завершён; воспроизводящий experiment.py
оставлен только в output/handoff как артефакт опыта.

## Подготовка к GitHub

Локальные три коммита до упаковки сохранены без переписывания. Проверены
63 разных исторических blob: секретов, личных абсолютных путей и мусора
не найдено. Remote Kwentin3/build123d при подготовке пустой и публичный;
доступ на запись подтверждён. Первая отправка требует подтверждения состава
пользователем; до него материалы готовятся только локально.

Все 68 pinned requirements имеют доступные в PyPI совместимые Windows x64 /
Python 3.13 wheels. Для полного теста чистого клона нужно сначала выполнить
исходный `models/mangal/model.py`: исследование клина читает его BOM/отчёт.
Порядок указан в README; геометрия, тесты и зависимости не менялись.

В [output/examples](output/examples/README.md) отобраны 17 исторических файлов
и два производных переносимых отчёта, всего с README около 1 MiB. Даты и
неподтверждённая текущая source binding указаны явно. PDF проверен на семь
страниц и содержимое, выбранные PNG открыты; личных путей в этом наборе нет.
Оригинальные результаты сохранены. Остальной output, среды, кэши, логи и
локальные evidence в Git не включаются. Правило attributes сохраняет байты
выбранных CAD-файлов при checkout, чтобы не нарушать их записанные SHA-256.

Чистый локальный клон кандидата `38d5992` восстановлен без прежнего output
и без основного `.venv`. В новом Python 3.13.7 venv из публичного PyPI
установлены все 68 точных версий, системные site-packages отключены;
версии сверены через metadata, `pip check` успешен. PowerShell перенаправление
stderr после установки дало технический ненулевой код оболочки; повторной
установки не было, завершённость подтверждена фактически установленными pins
и отдельной успешной проверкой окружения.

Команды первого запуска README выполнены: plate, исходный mangal и mangal_v21
получили geometry/execution PASS, измерения соответствуют заданию, STEP
повторно импортирован и проверен. Сверены 43 native source/dependency/artifact
привязки. Полный pytest в этом же чистом клоне: **70 passed за 345,92 с**,
без failures/errors/skips. Новый viewer/PDF не запускался; их опубликованные
примеры остаются историческими. Linux и другой компьютер/ОС не аттестованы.

Проверочный клон и его отдельное окружение удалены после завершения процессов;
компактные результаты проверки сохранены локально в `output/publish/` и
исключены из Git. Оригинальные 112 output-файлов сохранены. Публикация
подготовленного состава ожидает отдельного разрешения пользователя.
