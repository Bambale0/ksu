from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.db.models import Generation, Notification, PartnerWithdrawal, Payment, SupportMessage, SupportTicket
from app.db.notification_models import NotificationDelivery


def _money(value: Decimal | object) -> str:
    try:
        return f"{Decimal(value):.2f}".rstrip("0").rstrip(".")
    except Exception:  # noqa: BLE001 - notification copy must not break the business flush
        return str(value)


def _add_notification(
    session: Session,
    *,
    user_id: uuid.UUID,
    kind: str,
    title: str,
    body: str,
) -> None:
    notification_id = uuid.uuid4()
    session.add(
        Notification(
            id=notification_id,
            user_id=user_id,
            kind=kind,
            title=title,
            body=body,
            is_read=False,
        )
    )
    session.add(
        NotificationDelivery(
            id=uuid.uuid4(),
            notification_id=notification_id,
            channel="telegram",
            purpose="transactional",
            status="pending",
            attempts=0,
        )
    )


def _status_changed(obj: object) -> bool:
    state = inspect(obj)
    return bool(state.attrs.status.history.has_changes())


def _before_flush(session: Session, _flush_context: object, _instances: object) -> None:
    for obj in list(session.dirty):
        if isinstance(obj, Generation) and _status_changed(obj):
            if obj.status == "succeeded":
                _add_notification(
                    session,
                    user_id=obj.user_id,
                    kind="generation_succeeded",
                    title="Контент готов",
                    body="Генерация завершена. Результат доступен в истории.",
                )
            elif obj.status == "failed":
                _add_notification(
                    session,
                    user_id=obj.user_id,
                    kind="generation_failed",
                    title="Генерация не завершилась",
                    body="Задача завершилась с ошибкой. Проверьте историю и статус возврата кредитов.",
                )
        elif isinstance(obj, Payment) and _status_changed(obj):
            if obj.status == "succeeded":
                _add_notification(
                    session,
                    user_id=obj.user_id,
                    kind="payment_succeeded",
                    title="Баланс пополнен",
                    body=f"Оплата подтверждена. Начислено {_money(obj.rox_amount)} кредитов.",
                )
            elif obj.status in {"refunded", "partially_refunded", "chargeback"}:
                _add_notification(
                    session,
                    user_id=obj.user_id,
                    kind="payment_reversed",
                    title="Изменение по платежу",
                    body="По платежу зарегистрирован возврат или корректировка. Актуальный баланс доступен в кошельке.",
                )
        elif isinstance(obj, PartnerWithdrawal) and _status_changed(obj):
            if obj.status in {"processing", "paid", "rejected", "canceled"}:
                titles = {
                    "processing": "Вывод обрабатывается",
                    "paid": "Вывод выплачен",
                    "rejected": "Вывод отклонён",
                    "canceled": "Вывод отменён",
                }
                _add_notification(
                    session,
                    user_id=obj.user_id,
                    kind=f"partner_withdrawal_{obj.status}",
                    title=titles[obj.status],
                    body=f"Заявка на {_money(obj.amount)} ₽: {obj.status}.",
                )

    for obj in list(session.new):
        if isinstance(obj, SupportMessage) and obj.is_admin:
            ticket = session.get(SupportTicket, obj.ticket_id)
            if ticket is not None:
                _add_notification(
                    session,
                    user_id=ticket.user_id,
                    kind="support_reply",
                    title="Ответ поддержки",
                    body="В вашем обращении появился новый ответ.",
                )


def register_notification_events() -> None:
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)
