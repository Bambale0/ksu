# ЮKassa в ROXY

ЮKassa использует существующий серверный payment lifecycle KSU: локальный платёж создаётся до внешнего запроса, запрос к ЮKassa идемпотентен, а ROX начисляются только после подтверждённого статуса `succeeded`.

## Переменные окружения

```env
YOOKASSA_SHOP_ID=
YOOKASSA_SECRET_KEY=
YOOKASSA_BASE_URL=https://api.yookassa.ru
PAYMENT_RETURN_URL=https://<public-host>/mini-app/payments/
```

Если `PAYMENT_RETURN_URL` пуст, используется `PUBLIC_BASE_URL`. Для показа ЮKassa в Mini App должны быть заданы `YOOKASSA_SHOP_ID`, `YOOKASSA_SECRET_KEY` и один из публичных return URL.

## НПД: самозанятый без ИП

Интеграция KSU подходит для магазина, владельцем которого является физлицо —
самозанятый на НПД без статуса ИП. В этом режиме KSU отвечает только за
приём и сверку платежа в ЮKassa.

При создании платежа backend намеренно **не передаёт `receipt`**, данные
онлайн-кассы, НДС или `tax_system_code`. Эти поля относятся к сценариям
54-ФЗ для компаний и ИП и не должны автоматически добавляться в НПД-flow.
Контракт защищён отдельным тестом провайдера.

Типовой запрос KSU в ЮKassa содержит только:

```json
{
  "amount": {"value": "300.00", "currency": "RUB"},
  "capture": true,
  "confirmation": {
    "type": "redirect",
    "return_url": "https://<public-host>/mini-app/payments/"
  },
  "description": "ROX top-up",
  "metadata": {
    "payment_id": "<local-payment-uuid>"
  }
}
```

Важно различать приём платежа и НПД-чек. По актуальной документации ЮKassa
автоматическая регистрация дохода самозанятого в «Мой налог» через сервис
ЮKassa недоступна; поддержка старого сервиса чеков для самозанятых была
прекращена 29 декабря 2025 года. Поэтому KSU не помечает обычный
`payment.succeeded` как доказательство регистрации дохода в «Мой налог».

Если конкретный старый магазин ЮKassa продолжает автоматически формировать
НПД-чеки на стороне аккаунта/договора, KSU остаётся с таким legacy-сценарием
совместимым: payment payload не содержит 54-ФЗ-чек и не вмешивается в
аккаунтную фискализацию. Для нового магазина регистрацию дохода в «Мой налог»
нужно настраивать отдельно от этого payment flow.

Официальные материалы ЮKassa:

- https://yookassa.ru/developers/payment-acceptance/receipts/basics
- https://yookassa.ru/developers/using-api/changelog

Пакеты берутся из `ROX_PACKAGES_JSON`. Для текущей экономики ROXY валюта пакета должна быть `RUB`. Если в пакете указано только `amount` или только `credits`, недостающее значение рассчитывается по внутренней деноминации `1 ROX = 1 RUB`. Если указаны оба поля, это явная цена провайдера: начисляется указанное количество ROX, а списывается указанная сумма в RUB. Так можно синхронизировать ЮKassa с пакетами Lava Top.

Пример:

```env
ROX_PACKAGES_JSON={"lava-starter":{"amount":"108.70","credits":"100","currency":"RUB"},"lava-pro":{"amount":"1086.96","credits":"1000","currency":"RUB"}}
```

## Webhook

В личном кабинете ЮKassa укажите HTTPS URL:

```text
https://<public-host>/webhooks/payments/yookassa
```

Подпишите как минимум события:

- `payment.succeeded`;
- `payment.canceled`;
- `refund.succeeded`, если используются возвраты.

KSU не доверяет телу webhook как источнику истины: уведомление используется как сигнал, после чего backend запрашивает актуальный объект платежа у API ЮKassa и сверяет provider payment id, локальный `metadata.payment_id`, сумму и валюту до начисления ROX.

## Пользовательский flow

1. Пользователь открывает «Пополнения ROX» и выбирает «ЮKassa».
2. Mini App создаёт платёж через `POST /api/v1/payments` с `provider=yookassa` и уникальным `Idempotency-Key`.
3. Backend создаёт redirect-платёж ЮKassa и возвращает `confirmation_url`.
4. Mini App открывает платёжную страницу.
5. После `payment.succeeded` webhook сверяет платёж через API ЮKassa и начисляет ROX идемпотентно.
6. Если webhook задержался, пользователь может нажать «Проверить статус»; Mini App вызывает `POST /api/v1/payments/yookassa/{payment_id}/reconcile`.

Возвраты и частичные возвраты уже проходят через общий accounting lifecycle KSU: списание ранее начисленных ROX и связанная партнёрская бухгалтерия выполняются идемпотентно.
