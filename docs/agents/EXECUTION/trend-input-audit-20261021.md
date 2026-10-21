# Trend personalization input audit — 2026-10-21

Snapshot: **10:26 Moscow / 07:26 UTC**, production image/main `3567c9d8b25f8e7ed57640f947a0198a3eebee15`. The read-only inventory used an explicit READ ONLY transaction and 8-second statement timeout on the connected KSU host. No customer values or hidden prompts were exported.

## Scope and findings

All **283 stored trends** were inspected, including **276 active** and 7 inactive. There are **167 configured fields** in **116 trends**, with **58 distinct labels** and no legacy `{{…}}` tokens in this snapshot. Legacy-token behavior is separately regression-tested.

**13 active trends have incorrect inferred types on production:** 7 season fields, 4 weather fields, 1 season-options field, and 1 caption whose Birthday example triggered a date picker. The earlier narrow PR fixed only six season fields. The full correction repairs all 13 through normal read-time normalization, without SQL changes.

| Affected label | Active occurrences | Correct type |
| --- | ---: | --- |
| Время года | 5 | text |
| Время года (пример:зима) | 1 | text |
| Время года: | 1 | text |
| Погода | 4 | text |
| Сезон (зима/весна/лето/осень) | 1 | text |
| Надпись на газете (пример: «31th Birthday») | 1 | text |

The corrected snapshot has **92 numeric** and **75 text** fields. The only stored date type was the misclassified caption; real date labels are covered by synthetic compatibility tests.

Other Mini App numeric controls use explicit server `ui_schema.control` metadata or fixed semantic fields. The unbounded label-hint classifier existed only in the backend personalization helper and two copied admin functions; both admin editors now use one shared helper.

At the same boundary, tests reproduced five literal-text failures (backslashes interpreted as regex replacement syntax or user values re-expanded) and five invalid-calendar-date acceptances. One-pass literal substitution and canonical ISO calendar validation address them before generation/billing.

## Reviewed label corpus

The sanitized test fixture stores labels, expected types and occurrence counts only. No trend identifiers, hidden prompts or customer data are committed.

| Label | Expected type | All occurrences | Active occurrences |
| --- | --- | ---: | ---: |
| Возраст | number | 53 | 52 |
| Марка,модель автомобиля | text | 1 | 1 |
| Цвет автомобиля | text | 2 | 2 |
| Одежда | text | 15 | 15 |
| Возраст (цифры на капкейке) | number | 1 | 1 |
| Надпись | text | 6 | 6 |
| Погода | text | 4 | 4 |
| Прическа | text | 2 | 2 |
| Обувь | text | 3 | 3 |
| Очки | text | 1 | 1 |
| Свечи цифры | number | 13 | 13 |
| Вид животного | text | 1 | 1 |
| Знак зодиака | text | 2 | 2 |
| Цифры на торте | number | 2 | 2 |
| Год рождения | number | 2 | 2 |
| Время года (пример:зима) | text | 1 | 1 |
| Рост | number | 2 | 2 |
| Вес | number | 2 | 2 |
| Время года | text | 5 | 5 |
| Город | text | 2 | 2 |
| Надпись в лупе | text | 1 | 1 |
| Надпись на блокноте | text | 1 | 1 |
| Фамилия и Имя | text | 1 | 1 |
| Цифры | number | 4 | 4 |
| Цвет машины | text | 2 | 2 |
| Модель машины | text | 2 | 2 |
| Сумка | text | 2 | 2 |
| Кепка | text | 1 | 1 |
| Автомобиль (марка и модель) | text | 1 | 1 |
| Укажи год прошлого | number | 1 | 1 |
| Укажи год настоящего | number | 1 | 1 |
| Надпись проекция | text | 1 | 1 |
| Надпись на торте | text | 1 | 1 |
| Цифры на шаре | number | 1 | 1 |
| Мотоцикл | text | 1 | 1 |
| Шлем | text | 1 | 1 |
| Свеча цифра | number | 2 | 2 |
| Цвет шляпы | text | 1 | 1 |
| Цвет глаз | text | 1 | 1 |
| Срок беременности (пример: 5 месяцев) | text | 2 | 2 |
| Сезон (зима/весна/лето/осень) | text | 1 | 1 |
| Сезон | text | 1 | 1 |
| Время года: | text | 1 | 1 |
| Надпись (на англ.языке) пример: SCORPIO | text | 1 | 1 |
| Надпись на газете (пример: «31th Birthday») | text | 1 | 1 |
| Цифры свечи | number | 1 | 1 |
| Название страны | text | 1 | 1 |
| Месяц беременности | text | 1 | 1 |
| Цвет торта | text | 1 | 1 |
| Цвет платья | text | 1 | 1 |
| Число для шаров | number | 1 | 1 |
| Смартфон | text | 1 | 1 |
| Число | number | 1 | 1 |
| Число на свечах | number | 1 | 1 |
| Цифра на левой подошве: | number | 1 | 1 |
| Цифра на правой подошве: | number | 1 | 1 |
| Шары цифры | number | 2 | 2 |
| Срок беременности | text | 1 | 1 |

## Evidence and limits

A final read-only rescan at 2026-10-21T07:41:45.121913+00:00 confirmed that all inventoried schemas were unchanged.

- Read-only replay of all **283 schemas / 167 fields** using synthetic prompt placeholders and test values: **0 errors**, **13 type repairs**.
- Backend RED: 23 classification failures (catalog plus word/example collisions), 5 literal-value failures, 5 invalid-date acceptances. Configured and legacy paths are covered.
- GREEN: **231 focused backend checks**, including public-view repair and pre-generation invalid-date guards; all **33 Chromium journeys** passed, covering every reviewed label in the runner and both editors. Typecheck/static build, Ruff, compileall and diff checks passed; independent Standards/Spec review has no remaining findings.
- Build/typecheck, lint, exact-final-head backend/E2E/WebKit CI and independent review are delivery gates; their final exact SHA/results are recorded in PR #548 to avoid changing the verified commit after CI.
- This audits personalization schemas and synthetic input flows. It does not certify provider execution or generated-media quality for every trend. No paid generation, database mutation, production release or physical-iPhone test was performed.
