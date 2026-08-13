from __future__ import annotations

import uuid

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.handlers.admin import _admin_account
from app.bot.keyboards import back_menu
from app.services.admin_content import AdminContentService
from app.services.admin_exports import AdminExportService
from app.services.admin_generation_operations import AdminGenerationOperationService
from app.services.admin_partners import AdminPartnerService
from app.services.admin_promos import AdminPromoService

router = Router(name="admin-extensions")


def _back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")]]
    )


async def _message_admin(
    message: Message,
    session: AsyncSession,
    state: FSMContext | None = None,
):  # type: ignore[no-untyped-def]
    if message.from_user is None:
        return None
    admin = await _admin_account(session, message.from_user.id)
    if admin is None:
        if state is not None:
            await state.clear()
        await message.answer("Нет admin-доступа.", reply_markup=back_menu())
    return admin


async def _callback_admin(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext | None = None,
):  # type: ignore[no-untyped-def]
    admin = await _admin_account(session, callback.from_user.id)
    if admin is None:
        if state is not None:
            await state.clear()
        await callback.answer("Нет admin-доступа", show_alert=True)
    return admin


@router.message(Command("admin_tools"))
async def admin_tools(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if await _message_admin(message, session, state) is None:
        return
    await message.answer(
        "🧰 Дополнительные admin tools\n\n"
        "• /admin_export — CSV/XLSX финансы\n"
        "• /admin_promo CODE — lookup + activate/deactivate\n"
        "• /admin_withdrawal UUID — детали выплаты\n"
        "• /admin_prompt UUID — prompt moderation\n"
        "• /admin_generation UUID — privileged operation preview",
        reply_markup=_back(),
    )


@router.message(Command("admin_export"))
async def admin_export_menu(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if await _message_admin(message, session, state) is None:
        return
    await message.answer(
        "📤 Экспорт до 10 000 последних записей",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Payments CSV",
                        callback_data="adminx:export:payments:csv",
                    ),
                    InlineKeyboardButton(
                        text="Payments XLSX",
                        callback_data="adminx:export:payments:xlsx",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        text="Withdrawals CSV",
                        callback_data="adminx:export:withdrawals:csv",
                    ),
                    InlineKeyboardButton(
                        text="Withdrawals XLSX",
                        callback_data="adminx:export:withdrawals:xlsx",
                    ),
                ],
                [InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")],
            ]
        ),
    )


@router.callback_query(F.data.startswith("adminx:export:"))
async def admin_export_file(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    admin = await _callback_admin(callback, session, state)
    if admin is None:
        return
    _, _, kind, format_name = callback.data.split(":", 3)
    try:
        filename, _mime, content = await AdminExportService.export(
            session,
            admin=admin,
            kind=kind,
            format=format_name,
        )
    except Exception as exc:  # noqa: BLE001
        await callback.answer(str(exc)[:180], show_alert=True)
        return
    if isinstance(callback.message, Message):
        await callback.message.answer_document(
            BufferedInputFile(content, filename=filename),
            caption=f"Экспорт {kind} · {format_name.upper()}",
        )
    await callback.answer("Экспорт готов")


@router.message(Command("admin_promo"))
async def admin_promo_lookup(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    admin = await _message_admin(message, session, state)
    if admin is None:
        return
    query = str(command.args or "").strip()
    if not query:
        await message.answer("Использование: /admin_promo CODE_OR_UUID", reply_markup=_back())
        return
    try:
        promo = await AdminPromoService.lookup(session, admin=admin, query=query)
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"Не найдено: {exc}", reply_markup=_back())
        return
    target = not bool(promo["is_active"])
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Активировать" if target else "Деактивировать",
                    callback_data=(
                        f"adminx:promo:{promo['id']}:{1 if target else 0}"
                    ),
                )
            ],
            [InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")],
        ]
    )
    await message.answer(
        f"🎟 {promo['code']}\n"
        f"ID: {promo['id']}\n"
        f"Награда: {promo['reward_credits']} cr\n"
        f"Использовано: {promo['uses_count']}/{promo['max_uses'] or '∞'}\n"
        f"Статус: {'active' if promo['is_active'] else 'inactive'}\n"
        f"Expires: {promo['expires_at'] or '—'}",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("adminx:promo:"))
async def admin_promo_toggle(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    admin = await _callback_admin(callback, session, state)
    if admin is None:
        return
    _, _, promo_id, active = callback.data.split(":", 3)
    try:
        result, replayed = await AdminPromoService.set_active(
            session,
            admin=admin,
            promo_id=uuid.UUID(promo_id),
            is_active=active == "1",
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
        f"{'active' if result['is_active'] else 'inactive'} · replay={replayed}",
        show_alert=True,
    )


@router.message(Command("admin_withdrawal"))
async def admin_withdrawal_detail(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    admin = await _message_admin(message, session, state)
    if admin is None:
        return
    raw = str(command.args or "").strip()
    try:
        withdrawal_id = uuid.UUID(raw)
    except ValueError:
        await message.answer("Использование: /admin_withdrawal UUID", reply_markup=_back())
        return
    try:
        item = await AdminPartnerService.withdrawal_detail(
            session,
            admin=admin,
            withdrawal_id=withdrawal_id,
        )
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"Не найдено: {exc}", reply_markup=_back())
        return
    await message.answer(
        "💸 Withdrawal detail\n\n"
        f"ID: {item['id']}\n"
        f"User: {item['user_id']}\n"
        f"Amount: {item['amount']}\n"
        f"Status: {item['status']}\n"
        f"Requisites: {item['requisites']}\n"
        f"Created: {item['created_at']}",
        reply_markup=_back(),
    )


@router.message(Command("admin_prompt"))
async def admin_prompt_detail(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    admin = await _message_admin(message, session, state)
    if admin is None:
        return
    try:
        prompt_id = uuid.UUID(str(command.args or "").strip())
    except ValueError:
        await message.answer("Использование: /admin_prompt UUID", reply_markup=_back())
        return
    try:
        item = await AdminContentService.get_prompt(session, admin=admin, prompt_id=prompt_id)
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"Не найдено: {exc}", reply_markup=_back())
        return
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="Approve",
                    callback_data=f"adminx:prompt:{item['id']}:approve",
                ),
                InlineKeyboardButton(
                    text="Reject",
                    callback_data=f"adminx:prompt:{item['id']}:reject",
                ),
                InlineKeyboardButton(
                    text="Deactivate",
                    callback_data=f"adminx:prompt:{item['id']}:deactivate",
                ),
            ],
            [InlineKeyboardButton(text="⬅️ Админ", callback_data="admin:home")],
        ]
    )
    await message.answer(
        f"🧾 {item['title']}\nStatus: {item['status']} / active={item['is_active']}\n\n"
        f"{item['prompt'][:3000]}",
        reply_markup=keyboard,
    )


@router.callback_query(F.data.startswith("adminx:prompt:"))
async def admin_prompt_action(
    callback: CallbackQuery,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    admin = await _callback_admin(callback, session, state)
    if admin is None:
        return
    _, _, prompt_id, action = callback.data.split(":", 3)
    try:
        result, replayed = await AdminContentService.moderate_prompt(
            session,
            admin=admin,
            prompt_id=uuid.UUID(prompt_id),
            action=action,
            reason=f"{action} via Telegram admin detail",
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


@router.message(Command("admin_generation"))
async def admin_generation_preview(
    message: Message,
    command: CommandObject,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    admin = await _message_admin(message, session, state)
    if admin is None:
        return
    try:
        operation_id = uuid.UUID(str(command.args or "").strip())
    except ValueError:
        await message.answer("Использование: /admin_generation UUID", reply_markup=_back())
        return
    try:
        item = await AdminGenerationOperationService.get_operation(
            session,
            admin=admin,
            operation_id=operation_id,
        )
    except Exception as exc:  # noqa: BLE001
        await message.answer(f"Не найдено: {exc}", reply_markup=_back())
        return
    timeline = "\n".join(
        f"• {event['at']} · {event['type']} · {event.get('status') or event.get('kind') or ''}"
        for event in item["timeline"][-10:]
    )
    await message.answer(
        "🔬 Privileged generation preview\n\n"
        f"ID: {item['id']}\n"
        f"User: {item['user_id']}\n"
        f"Model/provider: {item['parameters'].get('_model_id') or '—'} / {item['provider']}\n"
        f"Status: {item['status']}\n"
        f"Cost: {item['cost_credits']} cr\n"
        f"Prompt: {item['prompt'][:1500]}\n"
        f"Error: {item['error'] or '—'}\n\n"
        f"Timeline:\n{timeline or '—'}",
        reply_markup=_back(),
    )
