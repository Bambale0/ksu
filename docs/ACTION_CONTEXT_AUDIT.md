# Generation Action Context Platform — Audit

Дата аудита: после внедрения foundation-слоя (`0032_generation_action_contexts`).
Цель документа — зафиксировать существующие потоки, точки интеграции и отклонения
новой платформы действий от них перед дальнейшими фазами (resolvers, capability,
telemetry, tests).

## Existing flow

### Backend

| Область | Файл | Роль |
| --- | --- | --- |
| Generation модель | `app/db/models.py` (`Generation`) | источник результата: `prompt`, `parameters`, `result_url`, `input_url`, `publication_scope`, `parent_generation_id` |
| Generation сервис | `app/services/generations.py`, `app/api/v1/generations.py` | создание генераций, quote, списания — единственный вход в pipeline |
| Действия над результатом | `app/services/generation_actions.py` | `GenerationActionService`: available/canonical actions, candidate models, default model, reusable parameters, reference adaptation |
| Media | `app/db/media_models.py` (`MediaAsset`) | готовые ассеты генерации (status/object_key/bucket) |
| Model catalog | `app/services/model_catalog.py` (`ModelSpec`, `SPECS`) | единственный источник правды по моделям: `media_type`, `operation`, `known_fields` |
| UI schema | `app/services/model_ui_contract.py` (`build_public_model_ui_schema`) | бэкенд генерирует UI; фронт не хранит бизнес-логику моделей |
| Billing | `app/services/wallet.py`, pricing resolver внутри `ModelCatalog.prepare` | quote и списание ROX |
| Feed | `app/services/feed.py`, `app/db/feed_models.py` | публикация, `share_payload()`, deep links |
| Auth | `app/api/deps.py` (`CurrentUserDep`, `SessionDep`, `RedisDep`) | Telegram initData auth |

### Action context foundation (уже внедрено)

* Модель: `app/db/action_context_models.py::GenerationActionContext`
  (`user_id`, `source_generation_id`, `action`, `target_mode`, `target_model_id`,
  `payload_json`, `status(active/executed/expired)`, `opened_count/at`,
  `executed_at`, `expires_at`).
* Миграция: `alembic/versions/0032_generation_action_contexts.py`
  (+ частичный unique index: одна active-строка на user/generation/action).
* Сервис: `app/services/generation_action_contexts.py`
  (`create_action_context`, `get_action_context`, `mark_action_context_executed`,
  `build_action_context_payload`). Owner-scoped, TTL 7 дней, идемпотентно.
* API: `app/api/v1/generation_actions.py` (execute производных действий),
  `app/api/v1/generation_action_contexts.py` (create/read контекста).
* Feature flags: `GENERATION_ACTION_CONTEXTS_ENABLED`,
  `GENERATION_ACTION_CONTEXT_TTL_SECONDS`.

### Frontend

* Точка входа сценариев: `frontend/mini-app/components/generation-action-app.tsx`
  — парсит `route=generation-action&action_context_id=…` (fallback:
  `generation=<id>&action=<id>`), грузит контекст, префиллит форму
  (prompt/references/model/параметры/billing), показывает quote до запуска.
* Publish success screen: компонент `PublishSuccess` — 🎉 + «Поделиться ссылкой»
  (`t.me/share/url`), «Скопировать ссылку», «Открыть публикацию».
* Telegram helpers: `frontend/mini-app/lib/telegram.ts` (`openTelegramShare`,
  `copyToClipboard`, haptics).
* Bot delivery: `app/workers/notifications.py` — кнопки под результатом создают
  серверный контекст и ведут в Mini App по `action_context_id`.

## Problems

1. **Логика резолва размазана** — выбор моделей/режимов для edit/animate живёт
   внутри `GenerationActionService.candidate_specs/_supports_image_source`;
   нет отдельного capability-слоя с интерфейсом `supports()/resolve_fallback()`.
2. **Нет формального enum действий** — канонические id (`remix`, `repeat`, `edit`,
   `animate`, `publish`) — строки; алиасы (`new_prompt/parameters → repeat`)
   размазаны по константе `ACTION_ALIASES`.
3. **Резолверы не выделены** — правила «remix копирует intent», «variation =
   тот же model/settings», «edit → i2i», «animate → i2v» не выражены как
   отдельные, тестируемые юниты.
4. **Ответ create-context** не содержит поля `action_context_id`/`route` из
   целевого контракта (только `id`/`open_app_url`).
5. **Нет alias-роута** `GET /api/v1/action-context/{id}` из целевого контракта.
6. **Телеметрия событий действий** отсутствует (только счётчики opened_count).
7. Падающий (предсуществующий) тест
   `tests/test_feed_domain.py::test_completed_image_generation_publishes_to_feed`
   связан с `FeedStaticStorage.public_prefix` и к платформе действий отношения
   не имеет — чинится отдельно.

## Integration points

* **Единственный pipeline генераций** — производные действия исполняются через
  существующий `POST /generations/{id}/actions/{action}` → `GenerationService`;
  новые слои только готовят контекст/префилл и никогда не запускают генерацию сами.
* **Model catalog** — capability-слой читает `ModelCatalog.list()/get()` и поля
  `ModelSpec`; дублирование конфигурации моделей запрещено.
* **ui_schema** — кандидаты всегда отдаются через `build_public_model_ui_schema`;
  фронт рендерит форму исключительно из схемы.
* **Billing** — quote считается штатным `/generations/quote` до подтверждения;
  резолверы выставляют только флаг «требуется подтверждение цены».
* **Feed/publish** — publish-resolver переиспользует `FeedService.share_payload()`
  и правило «публиковать может только автор»; новых таблиц ленты нет.
* **Auth** — все контексты owner-scoped (`user_id == context.user_id`), чужие
  контексты отвечают 404 без утечки существования.

## Proposed changes

1. `app/services/generation_actions/` — пакет вместо модуля (публичный API
   сохраняется через `__init__.py`): `types.py` (enum `GenerationActionType`),
   `core.py` (бывший monolith), `base.py` + `remix.py` / `variation.py` /
   `edit_image.py` / `animate.py` / `publish.py` (резолверы).
2. `app/services/model_capability.py` — `ModelCapabilityResolver`
   (`supports(mode)`, `supports_input(type)`, `compatible_specs()`,
   `resolve_fallback()`); `GenerationActionService` делегирует выбор ему.
3. Контрактные дополнения API: `action_context_id` + `route` в ответе
   create, alias `GET /action-context/{id}`.
4. `app/services/action_telemetry.py` — структурированные события
   (`action_context_created/opened`, `action_executed`, `publish_success`, …)
   поверх стандартного logging (OTel уже подключён глобально).
5. Тесты: `tests/test_resolvers.py` (capability + резолверы + права),
   расширение существующих `tests/test_generation_action_contexts.py`.

### Отклонения от буквы спецификации (осознанные)

* Имя сервиса — `generation_action_contexts.py` (множественное число), чтобы не
  конфликтовать с пакетом `generation_actions/`; контракт методов тот же
  (`create_context / validate / resolve / consume ≡ mark_executed`).
* Поле `source_media_id` в БД не выделено отдельной колонкой — исходное медиа
  однозначно восстанавливается из `payload_json.source_url` + `source_generation_id`
  (у генерации один результат); добавление колонки возможно миграцией позже.
* Маршрут Mini App — query-based (`?route=generation-action&action_context_id=`),
  т.к. Mini App использует query-роутинг, а не path-роутинг; семантика
  `/action/:context_id` сохранена.