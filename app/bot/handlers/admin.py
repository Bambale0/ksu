from __future__ import annotations

import json
import uuid
from decimal import Decimal, InvalidOperation

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    WebAppInfo,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import back_menu
from app.core.config import settings
from app.db.models import AdminAccount
from app.services.admin_ai import AdminAiService
from app.services.admin_content import AdminContentService
from app.services.admin_notifications import AdminNotificationService
from app.services.admin_partners import AdminPartnerService
from app.services.admin_pricing import AdminPricingService
from app.services.admin_promos import AdminPromoService
from app.services.admin_reporting import AdminReportingService
from app.services.admin_runtime import AdminRuntimeService
from app.services.admin_users import AdminUserService
from app.services.users import UserService

router = Router(name="admin-launch")

CONFIRM_PHRASE = "ПОДТВЕРЖДАЮ"


class AdminStates(StatesGroup):
    user_lookup = State()
    balance_amount = State()
    balance_reason = State()
    balance_confirm = State()
    block_reason = State()
    block_confirm = State()
    promo_create = State()
    pricing_json = State()
    pricing_confirm = State()
    broadcast_title = State()
    broadcast_body = State()
    broadcast_confirm = State()
    withdrawal_reason = State()
    withdrawal_confirm = State()


def _main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📊 Сводка", callback_data="admin:summary"),
                InlineKeyboardButton(text="👤 Пользователь", callback_data="admin:user"),
            ],
            [
                InlineKeyboardButton(text="💰 Финансы", callback_data="admin:finance"),
                InlineKeyboardButton(text="🤝 Партнёры", callback_data="admin:partners"),
            ],
            [
                InlineKeyboardButton(text="💸 Выплаты", callback_data="admin:withdrawals"),
                InlineKeyboardButton(text="🏷 Тарифы", callback_data="admin:pricing"),
            ],
            [
                InlineKeyboardButton(text="🎟 Промо", callback_data="admin:promos"),
                InlineKeyboardButton(text="🧾 Промпты", callback_data="admin:prompts"),
            ],
            [
                InlineKeyboardButton(text="📣 Рассылка", callback_data="admin:broadcast"),
                InlineKeyboardButton(text="⚙️ Runtime", callback_data="admin:runtime"),
            ],
            [InlineKeyboardButton(text="🧠 AI admin", callback_data="admin:ai")],
            [InlineKeyboardButton(text="🌐 Web console", callback_data="admin:web")],
            [InlineKeyboardButton(text="⬅️ В главное меню", callback_data="nav:main")],
        ]
    )


def _back_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")]]
    )


async def _admin_account(
    session: AsyncSession,
    telegram_id: int,
) -> AdminAccount | None:
    user = await UserService.get_by_telegram_id(session, telegram_id)
    if user is None:
        return None
    return await session.scalar(
        select(AdminAccount).where(
            AdminAccount.user_id == user.id,
            AdminAccount.is_active.is_(True),
        )
    )


async def _require_message_admin(
    message: Message,
    session: AsyncSession,
    state: FSMContext | None = None,
) -> AdminAccount | None:
    if message.from_user is None:
        return None
    admin = await _admin_account(session, message.from_user.id)
    if admin is None:
        if state is not None:
            await state.clear()
        await message.answer("Админ-доступ больше не активен.", reply_markup=back_menu())
    return admin


async def _require_callback_admin(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext | None = None,
) -> AdminAccount | None:
    admin = await _admin_account(session, callback.from_user.id)
    if admin is None:
        if state is not None:
            await state.clear()
        await callback.answer("Нет admin-доступа", show_alert=True)
    return admin


def _fmt_summary(data: dict[str, object]) -> str:
    users = data["users"]
    generations = data["generations"]
    support = data["support"]
    withdrawals = data["withdrawals"]
    payments = data["payments"]
    return (
        "📊 Admin summary\n\n"
        f"Пользователи: {users['active']} активных / {users['total']} всего\n"
        f"Генерации: {generations['active']} активных, {generations['failed']} failed\n"
        f"Support: {support['open']} открытых\n"
        f"Выплаты: {withdrawals['pending_or_processing']} в очереди\n"
        f"Платежи: {payments['succeeded']} succeeded, {payments['amount']} {payments.get('currency', '')}\n"
        f"Начислено кредитов: {payments['credits']}"
    )


async def _send_or_edit(callback: CallbackQuery, text: str, keyboard: InlineKeyboardMarkup) -> None:
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.message(Command("admin"))
async def admin_console(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_message_admin(message, session, state)
    if admin is None:
        return
    await state.clear()
    await message.answer(
        "🛡 Админ-контур\n\nВсе write-действия проходят через общий policy/audit/idempotency слой.",
        reply_markup=_main_keyboard(),
    )


@router.callback_query(F.data == "admin:home")
async def admin_home(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if await _require_callback_admin(callback, session, state) is None:
        return
    await state.clear()
    await _send_or_edit(callback, "🛡 Админ-контур", _main_keyboard())


@router.callback_query(F.data == "admin:web")
async def admin_web(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if await _require_callback_admin(callback, session, state) is None:
        return
    if not settings.public_base_url:
        await callback.answer("PUBLIC_BASE_URL не настроен", show_alert=True)
        return
    url = f"{settings.public_base_url.rstrip('/')}/admin-app/"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🛡 Открыть web admin",
                    web_app=WebAppInfo(url=url),
                )
            ],
            [InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")],
        ]
    )
    await _send_or_edit(
        callback,
        "Web admin использует отдельную admin-сессию и MFA; Telegram-кнопка не является авторизацией.",
        keyboard,
    )


@router.callback_query(F.data == "admin:summary")
async def admin_summary(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_callback_admin(callback, session, state)
    if admin is None:
        return
    data = await AdminReportingService.summary(session, admin=admin)
    await _send_or_edit(callback, _fmt_summary(data), _back_admin())


@router.callback_query(F.data == "admin:finance")
async def admin_finance(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_callback_admin(callback, session, state)
    if admin is None:
        return
    data = await AdminReportingService.finance(session, admin=admin)
    payment_lines = [
        f"• {row['currency']} / {row['status']}: {row['count']} шт., {row['amount']}"
        for row in data["payments"][:20]
    ]
    withdrawal_lines = [
        f"• {row['status']}: {row['count']} шт., {row['amount']}"
        for row in data["withdrawals"][:20]
    ]
    text = (
        "💰 Финансы\n\nПлатежи:\n"
        + ("\n".join(payment_lines) or "—")
        + "\n\nВыплаты:\n"
        + ("\n".join(withdrawal_lines) or "—")
        + f"\n\nWallet tx: {data['wallet']['transactions']}, net credits: {data['wallet']['net_credits']}"
    )
    await _send_or_edit(callback, text[:3900], _back_admin())


@router.callback_query(F.data == "admin:partners")
async def admin_partners(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_callback_admin(callback, session, state)
    if admin is None:
        return
    data = await AdminPartnerService.analytics(session, admin=admin)
    rewards = "\n".join(
        f"• {row['status']}: {row['count']} / {row['amount']}"
        for row in data["rewards"]
    )
    withdrawals = "\n".join(
        f"• {row['status']}: {row['count']} / {row['amount']}"
        for row in data["withdrawals"]
    )
    await _send_or_edit(
        callback,
        f"🤝 Партнёры\n\nСвязей: {data['referral_relations']}\n\nRewards:\n{rewards or '—'}\n\nWithdrawals:\n{withdrawals or '—'}",
        _back_admin(),
    )


@router.callback_query(F.data == "admin:user")
async def admin_user_start(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if await _require_callback_admin(callback, session, state) is None:
        return
    await state.set_state(AdminStates.user_lookup)
    await _send_or_edit(
        callback,
        "👤 Отправьте Telegram ID, internal UUID, username или имя пользователя.",
        _back_admin(),
    )


@router.message(AdminStates.user_lookup)
async def admin_user_lookup(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_message_admin(message, session, state)
    if admin is None or not message.text:
        return
    result = await AdminUserService.list_users(
        session,
        admin=admin,
        q=message.text,
        limit=10,
        offset=0,
    )
    await state.clear()
    if not result["items"]:
        await message.answer("Пользователь не найден.", reply_markup=_back_admin())
        return
    rows = result["items"]
    lines = [
        f"{index + 1}. {row['id']} | tg={row['telegram_id']} | @{row['username'] or '-'} | {row['balance_credits']} cr | {'active' if row['is_active'] else 'blocked'}"
        for index, row in enumerate(rows)
    ]
    keyboard_rows = []
    for index, row in enumerate(rows):
        user_id = row["id"]
        keyboard_rows.append(
            [
                InlineKeyboardButton(
                    text=f"{index + 1}: баланс",
                    callback_data=f"admin:user:balance:{user_id}",
                ),
                InlineKeyboardButton(
                    text=f"{index + 1}: {'block' if row['is_active'] else 'unblock'}",
                    callback_data=f"admin:user:block:{user_id}:{1 if row['is_active'] else 0}",
                ),
            ]
        )
    keyboard_rows.append([InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")])
    await message.answer(
        "👤 Результаты\n\n" + "\n".join(lines),
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard_rows),
    )


@router.callback_query(F.data.startswith("admin:user:balance:"))
async def admin_balance_start(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if await _require_callback_admin(callback, session, state) is None:
        return
    user_id = callback.data.rsplit(":", 1)[-1]
    await state.set_state(AdminStates.balance_amount)
    await state.update_data(target_user_id=user_id)
    await _send_or_edit(
        callback,
        "Введите изменение баланса в кредитах. Положительное число — начислить, отрицательное — списать.",
        _back_admin(),
    )


@router.message(AdminStates.balance_amount)
async def admin_balance_amount(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if await _require_message_admin(message, session, state) is None or not message.text:
        return
    try:
        amount = Decimal(message.text.replace(",", ".").strip())
    except InvalidOperation:
        await message.answer("Нужно число, например 25 или -10.")
        return
    if amount == 0 or abs(amount) > Decimal("100000"):
        await message.answer("Изменение должно быть от -100000 до 100000 и не равно нулю.")
        return
    await state.update_data(amount=str(amount))
    await state.set_state(AdminStates.balance_reason)
    await message.answer("Укажите причину изменения баланса.")


@router.message(AdminStates.balance_reason)
async def admin_balance_reason(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if await _require_message_admin(message, session, state) is None or not message.text:
        return
    reason = message.text.strip()
    if len(reason) < 5:
        await message.answer("Причина слишком короткая.")
        return
    data = await state.get_data()
    await state.update_data(reason=reason, idempotency_key=f"tg:{uuid.uuid4()}")
    await state.set_state(AdminStates.balance_confirm)
    await message.answer(
        f"Баланс пользователя {data['target_user_id']} изменить на {data['amount']} кредитов.\nПричина: {reason}\n\nВведите {CONFIRM_PHRASE} для выполнения.",
        reply_markup=_back_admin(),
    )


@router.message(AdminStates.balance_confirm)
async def admin_balance_confirm(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_message_admin(message, session, state)
    if admin is None or not message.text:
        return
    if message.text.strip().upper() != CONFIRM_PHRASE:
        await message.answer(f"Для выполнения введите ровно: {CONFIRM_PHRASE}")
        return
    data = await state.get_data()
    try:
        result, replayed = await AdminUserService.adjust_balance(
            session,
            admin=admin,
            user_id=uuid.UUID(data["target_user_id"]),
            amount=Decimal(data["amount"]),
            reason=data["reason"],
            idempotency_key=data["idempotency_key"],
            request_id=f"telegram:{message.message_id}",
            confirmed=True,
            step_up_valid=True,
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        await state.clear()
        await message.answer(f"Операция отклонена: {exc}", reply_markup=_back_admin())
        return
    await state.clear()
    await message.answer(
        f"✅ Баланс изменён. Новый баланс: {result['balance_after']} cr. Replay={replayed}",
        reply_markup=_back_admin(),
    )


@router.callback_query(F.data.startswith("admin:user:block:"))
async def admin_block_start(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if await _require_callback_admin(callback, session, state) is None:
        return
    _, _, _, user_id, active = callback.data.split(":", 4)
    blocked = active == "1"
    await state.update_data(
        target_user_id=user_id,
        blocked=blocked,
        idempotency_key=f"tg:{uuid.uuid4()}",
    )
    await state.set_state(AdminStates.block_reason)
    await _send_or_edit(
        callback,
        f"Введите причину {'блокировки' if blocked else 'разблокировки'} пользователя {user_id}.",
        _back_admin(),
    )


@router.message(AdminStates.block_reason)
async def admin_block_reason(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if await _require_message_admin(message, session, state) is None or not message.text:
        return
    reason = message.text.strip()
    if len(reason) < 5:
        await message.answer("Причина слишком короткая.")
        return
    await state.update_data(reason=reason)
    await state.set_state(AdminStates.block_confirm)
    await message.answer(f"Введите {CONFIRM_PHRASE} для выполнения.")


@router.message(AdminStates.block_confirm)
async def admin_block_confirm(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_message_admin(message, session, state)
    if admin is None or not message.text:
        return
    if message.text.strip().upper() != CONFIRM_PHRASE:
        await message.answer(f"Введите ровно: {CONFIRM_PHRASE}")
        return
    data = await state.get_data()
    try:
        result, replayed = await AdminUserService.set_blocked(
            session,
            admin=admin,
            user_id=uuid.UUID(data["target_user_id"]),
            blocked=bool(data["blocked"]),
            reason=data["reason"],
            idempotency_key=data["idempotency_key"],
            request_id=f"telegram:{message.message_id}",
            confirmed=True,
            step_up_valid=True,
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        await state.clear()
        await message.answer(f"Операция отклонена: {exc}", reply_markup=_back_admin())
        return
    await state.clear()
    await message.answer(
        f"✅ User status: {'active' if result['is_active'] else 'blocked'}. Replay={replayed}",
        reply_markup=_back_admin(),
    )


@router.callback_query(F.data == "admin:withdrawals")
async def admin_withdrawals(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_callback_admin(callback, session, state)
    if admin is None:
        return
    data = await AdminPartnerService.list_withdrawals(session, admin=admin, limit=10)
    rows = data["items"]
    text = "💸 Выплаты\n\n" + (
        "\n".join(
            f"{idx + 1}. {item['id']} | {item['amount']} | {item['status']}"
            for idx, item in enumerate(rows)
        )
        or "Очередь пуста."
    )
    keyboard = []
    for idx, item in enumerate(rows):
        if item["status"] in {"pending", "processing"}:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        text=f"{idx + 1}: processing",
                        callback_data=f"admin:wd:{item['id']}:processing",
                    ),
                    InlineKeyboardButton(
                        text=f"{idx + 1}: paid",
                        callback_data=f"admin:wd:{item['id']}:paid",
                    ),
                    InlineKeyboardButton(
                        text=f"{idx + 1}: reject",
                        callback_data=f"admin:wd:{item['id']}:rejected",
                    ),
                ]
            )
    keyboard.append([InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")])
    await _send_or_edit(callback, text[:3900], InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("admin:wd:"))
async def admin_withdrawal_action(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if await _require_callback_admin(callback, session, state) is None:
        return
    _, _, withdrawal_id, target_status = callback.data.split(":", 3)
    await state.update_data(
        withdrawal_id=withdrawal_id,
        withdrawal_status=target_status,
        idempotency_key=f"tg:{uuid.uuid4()}",
    )
    await state.set_state(AdminStates.withdrawal_reason)
    await _send_or_edit(callback, "Укажите причину изменения статуса выплаты.", _back_admin())


@router.message(AdminStates.withdrawal_reason)
async def admin_withdrawal_reason(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if await _require_message_admin(message, session, state) is None or not message.text:
        return
    if len(message.text.strip()) < 3:
        await message.answer("Причина слишком короткая.")
        return
    await state.update_data(reason=message.text.strip())
    await state.set_state(AdminStates.withdrawal_confirm)
    await message.answer(f"Введите {CONFIRM_PHRASE} для выполнения.")


@router.message(AdminStates.withdrawal_confirm)
async def admin_withdrawal_confirm(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_message_admin(message, session, state)
    if admin is None or not message.text:
        return
    if message.text.strip().upper() != CONFIRM_PHRASE:
        await message.answer(f"Введите ровно: {CONFIRM_PHRASE}")
        return
    data = await state.get_data()
    try:
        result, replayed = await AdminPartnerService.update_withdrawal(
            session,
            admin=admin,
            withdrawal_id=uuid.UUID(data["withdrawal_id"]),
            status=data["withdrawal_status"],
            reason=data["reason"],
            idempotency_key=data["idempotency_key"],
            request_id=f"telegram:{message.message_id}",
            confirmed=True,
            step_up_valid=True,
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        await state.clear()
        await message.answer(f"Операция отклонена: {exc}", reply_markup=_back_admin())
        return
    await state.clear()
    await message.answer(
        f"✅ Выплата: {result['status']}. Replay={replayed}",
        reply_markup=_back_admin(),
    )


@router.callback_query(F.data == "admin:promos")
async def admin_promos(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_callback_admin(callback, session, state)
    if admin is None:
        return
    data = await AdminPromoService.list_promos(session, admin=admin, limit=10)
    lines = [
        f"• {item['code']}: {item['reward_credits']} cr | {item['uses_count']}/{item['max_uses'] or '∞'} | {'on' if item['is_active'] else 'off'}"
        for item in data["items"]
    ]
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Создать", callback_data="admin:promo:create")],
            [InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")],
        ]
    )
    await _send_or_edit(callback, "🎟 Промо\n\n" + ("\n".join(lines) or "—"), keyboard)


@router.callback_query(F.data == "admin:promo:create")
async def admin_promo_create_start(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if await _require_callback_admin(callback, session, state) is None:
        return
    await state.set_state(AdminStates.promo_create)
    await _send_or_edit(
        callback,
        "Формат: CODE CREDITS MAX_USES\nПример: START100 100 500\nДля безлимита вместо MAX_USES укажите -",
        _back_admin(),
    )


@router.message(AdminStates.promo_create)
async def admin_promo_create(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_message_admin(message, session, state)
    if admin is None or not message.text:
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Нужно три значения: CODE CREDITS MAX_USES|-.")
        return
    try:
        reward = Decimal(parts[1].replace(",", "."))
        max_uses = None if parts[2] == "-" else int(parts[2])
        result, replayed = await AdminPromoService.create(
            session,
            admin=admin,
            code=parts[0],
            reward_credits=reward,
            max_uses=max_uses,
            expires_at=None,
            idempotency_key=f"tg:{uuid.uuid4()}",
            request_id=f"telegram:{message.message_id}",
            confirmed=True,
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        await message.answer(f"Не создано: {exc}")
        return
    await state.clear()
    await message.answer(
        f"✅ Промо {result['code']} создан. Replay={replayed}", reply_markup=_back_admin()
    )


@router.callback_query(F.data == "admin:pricing")
async def admin_pricing(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_callback_admin(callback, session, state)
    if admin is None:
        return
    current = await AdminPricingService.current(session, admin=admin)
    text = "🏷 Тарифы\n\n"
    if current:
        text += f"Published v{current['version']}\n{json.dumps(current['payload'], ensure_ascii=False, indent=2)[:2500]}"
    else:
        text += "Опубликованной версии пока нет."
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ Опубликовать JSON", callback_data="admin:pricing:publish")],
            [InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")],
        ]
    )
    await _send_or_edit(callback, text[:3900], keyboard)


@router.callback_query(F.data == "admin:pricing:publish")
async def admin_pricing_publish_start(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if await _require_callback_admin(callback, session, state) is None:
        return
    await state.set_state(AdminStates.pricing_json)
    await _send_or_edit(
        callback,
        "Отправьте JSON с секциями packages/image_prices/video_prices/partner_exchange/prompt_costs/video_prompt_costs/generation_pricing.",
        _back_admin(),
    )


@router.message(AdminStates.pricing_json)
async def admin_pricing_json(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if await _require_message_admin(message, session, state) is None or not message.text:
        return
    try:
        payload = json.loads(message.text)
    except json.JSONDecodeError as exc:
        await message.answer(f"Некорректный JSON: {exc}")
        return
    if not isinstance(payload, dict):
        await message.answer("Корневое значение должно быть JSON object.")
        return
    await state.update_data(tariff_payload=payload, idempotency_key=f"tg:{uuid.uuid4()}")
    await state.set_state(AdminStates.pricing_confirm)
    await message.answer(
        f"Preview:\n{json.dumps(payload, ensure_ascii=False, indent=2)[:3000]}\n\nВведите {CONFIRM_PHRASE} для публикации."
    )


@router.message(AdminStates.pricing_confirm)
async def admin_pricing_confirm(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_message_admin(message, session, state)
    if admin is None or not message.text:
        return
    if message.text.strip().upper() != CONFIRM_PHRASE:
        await message.answer(f"Введите ровно: {CONFIRM_PHRASE}")
        return
    data = await state.get_data()
    try:
        result, replayed = await AdminPricingService.publish(
            session,
            admin=admin,
            payload=data["tariff_payload"],
            idempotency_key=data["idempotency_key"],
            request_id=f"telegram:{message.message_id}",
            confirmed=True,
            step_up_valid=True,
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        await state.clear()
        await message.answer(f"Тариф не опубликован: {exc}", reply_markup=_back_admin())
        return
    await state.clear()
    await message.answer(
        f"✅ Tariff v{result['version']} published. Replay={replayed}", reply_markup=_back_admin()
    )


@router.callback_query(F.data == "admin:prompts")
async def admin_prompts(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_callback_admin(callback, session, state)
    if admin is None:
        return
    data = await AdminContentService.list_prompts(session, admin=admin, status="pending", limit=10)
    rows = data["items"]
    text = "🧾 Pending prompts\n\n" + (
        "\n\n".join(
            f"{idx + 1}. {item['title']}\n{item['prompt'][:250]}" for idx, item in enumerate(rows)
        )
        or "Очередь пуста."
    )
    keyboard = []
    for idx, item in enumerate(rows):
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=f"{idx + 1}: approve",
                    callback_data=f"admin:prompt:{item['id']}:approve",
                ),
                InlineKeyboardButton(
                    text=f"{idx + 1}: reject",
                    callback_data=f"admin:prompt:{item['id']}:reject",
                ),
            ]
        )
    keyboard.append([InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")])
    await _send_or_edit(callback, text[:3900], InlineKeyboardMarkup(inline_keyboard=keyboard))


@router.callback_query(F.data.startswith("admin:prompt:"))
async def admin_prompt_moderate(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_callback_admin(callback, session, state)
    if admin is None:
        return
    _, _, prompt_id, action = callback.data.split(":", 3)
    try:
        result, replayed = await AdminContentService.moderate_prompt(
            session,
            admin=admin,
            prompt_id=uuid.UUID(prompt_id),
            action=action,
            reason=f"{action} via Telegram admin preview",
            idempotency_key=f"tg:{uuid.uuid4()}",
            request_id=f"telegram-callback:{callback.id}",
            confirmed=True,
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        await callback.answer(str(exc)[:180], show_alert=True)
        return
    await callback.answer(f"{result['status']} · replay={replayed}", show_alert=True)
    await admin_prompts(callback, session, state)


@router.callback_query(F.data == "admin:broadcast")
async def admin_broadcast_start(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if await _require_callback_admin(callback, session, state) is None:
        return
    await state.set_state(AdminStates.broadcast_title)
    await _send_or_edit(callback, "📣 Введите заголовок рассылки.", _back_admin())


@router.message(AdminStates.broadcast_title)
async def admin_broadcast_title(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if await _require_message_admin(message, session, state) is None or not message.text:
        return
    title = message.text.strip()
    if not 1 <= len(title) <= 255:
        await message.answer("Заголовок: 1..255 символов.")
        return
    await state.update_data(broadcast_title=title)
    await state.set_state(AdminStates.broadcast_body)
    await message.answer("Введите текст рассылки (до 4000 символов).")


@router.message(AdminStates.broadcast_body)
async def admin_broadcast_body(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_message_admin(message, session, state)
    if admin is None or not message.text:
        return
    body = message.text.strip()
    if not 1 <= len(body) <= 4000:
        await message.answer("Текст: 1..4000 символов.")
        return
    data = await state.get_data()
    message_payload = {"title": data["broadcast_title"], "body": body}
    preview = await AdminNotificationService.preview_campaign(
        session,
        admin=admin,
        segment={"active_only": True},
        message=message_payload,
    )
    await state.update_data(
        broadcast_body=body,
        idempotency_key=f"tg:{uuid.uuid4()}",
    )
    await state.set_state(AdminStates.broadcast_confirm)
    await message.answer(
        f"Preview: {preview['recipient_count']} активных получателей.\n\n{data['broadcast_title']}\n\n{body}\n\nВведите {CONFIRM_PHRASE} для создания и запуска durable campaign."
    )


@router.message(AdminStates.broadcast_confirm)
async def admin_broadcast_confirm(message: Message, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_message_admin(message, session, state)
    if admin is None or not message.text:
        return
    if message.text.strip().upper() != CONFIRM_PHRASE:
        await message.answer(f"Введите ровно: {CONFIRM_PHRASE}")
        return
    data = await state.get_data()
    try:
        created, _ = await AdminNotificationService.create_campaign(
            session,
            admin=admin,
            name=f"Telegram broadcast {message.message_id}",
            segment={"active_only": True},
            message={"title": data["broadcast_title"], "body": data["broadcast_body"]},
            idempotency_key=data["idempotency_key"] + ":create",
            request_id=f"telegram:{message.message_id}:create",
        )
        started, replayed = await AdminNotificationService.start_campaign(
            session,
            admin=admin,
            campaign_id=uuid.UUID(created["id"]),
            idempotency_key=data["idempotency_key"] + ":start",
            request_id=f"telegram:{message.message_id}:start",
            confirmed=True,
            step_up_valid=True,
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        await state.clear()
        await message.answer(f"Рассылка не запущена: {exc}", reply_markup=_back_admin())
        return
    await state.clear()
    await message.answer(
        f"✅ Campaign {started['campaign_id']} запущен: {started['total_deliveries']} deliveries. Replay={replayed}",
        reply_markup=_back_admin(),
    )


@router.callback_query(F.data == "admin:runtime")
async def admin_runtime(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_callback_admin(callback, session, state)
    if admin is None:
        return
    values = await AdminRuntimeService.get_settings(session, admin=admin)
    required = bool((values.get("subscription_required") or {}).get("enabled"))
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Subscription required: {'ON' if required else 'OFF'}",
                    callback_data=f"admin:runtime:subscription:{0 if required else 1}",
                )
            ],
            [InlineKeyboardButton(text="♻️ Reload pricing", callback_data="admin:runtime:reload")],
            [InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")],
        ]
    )
    await _send_or_edit(callback, "⚙️ Runtime settings", keyboard)


@router.callback_query(F.data.startswith("admin:runtime:subscription:"))
async def admin_runtime_subscription(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    admin = await _require_callback_admin(callback, session, state)
    if admin is None:
        return
    enabled = callback.data.endswith(":1")
    try:
        _, replayed = await AdminRuntimeService.set_subscription_required(
            session,
            admin=admin,
            enabled=enabled,
            idempotency_key=f"tg:{uuid.uuid4()}",
            request_id=f"telegram-callback:{callback.id}",
            confirmed=True,
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        await callback.answer(str(exc)[:180], show_alert=True)
        return
    await callback.answer(f"Updated · replay={replayed}")
    await admin_runtime(callback, session, state)


@router.callback_query(F.data == "admin:runtime:reload")
async def admin_runtime_reload(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_callback_admin(callback, session, state)
    if admin is None:
        return
    try:
        result, replayed = await AdminRuntimeService.reload_runtime_config(
            session,
            admin=admin,
            idempotency_key=f"tg:{uuid.uuid4()}",
            request_id=f"telegram-callback:{callback.id}",
            confirmed=True,
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001
        await session.rollback()
        await callback.answer(str(exc)[:180], show_alert=True)
        return
    await callback.answer(
        f"Reloaded: {result['models_with_overrides']} overrides · replay={replayed}",
        show_alert=True,
    )


@router.callback_query(F.data == "admin:ai")
async def admin_ai(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    admin = await _require_callback_admin(callback, session, state)
    if admin is None:
        return
    data = await AdminAiService.brief(session, admin=admin)
    lines = [f"• [{item['priority']}] {item['action']}" for item in data["recommendations"]]
    await _send_or_edit(
        callback,
        "🧠 AI admin / operational copilot\n\n" + "\n".join(lines),
        _back_admin(),
    )
