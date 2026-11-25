from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from redis.asyncio import Redis

from app.core.config import settings
from app.services import browser_approval as approval
from app.services.feed_links import start_payload

router = Router(name="browser_approval")


def private_owner(message: Message, owner: int) -> bool:
    return message.chat.type == "private" and message.chat.id == owner


@router.message(CommandStart(deep_link=True, magic=F.args.startswith("auth_")))
async def start_browser_approval(message: Message, redis: Redis) -> None:
    if not message.from_user or not private_owner(message, message.from_user.id):
        return
    ticket = (start_payload(message.text) or "")[5:]
    result = await approval.transition(redis, ticket, "bind", owner=message.from_user.id)
    if result[0] != "pending":
        await message.answer("Запрос входа недоступен или истёк. Начни новый вход на сайте ROXY.")
        return
    text = (
        "Вы запрашивали вход на сайт ROXY?\n\n"
        f"Код проверки: {result[1]}\n"
        "Сравните его с кодом на сайте. Если это не вы — нажмите «Отклонить».\n"
        "Запрос действует 5 минут."
    )
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Подтвердить", callback_data="wa:y:" + ticket),
        InlineKeyboardButton(text="❌ Отклонить", callback_data="wa:n:" + ticket),
    ]]))


@router.callback_query(F.data.startswith("wa:"))
async def decide_browser_approval(callback: CallbackQuery, redis: Redis) -> None:
    if not isinstance(callback.message, Message) or not private_owner(callback.message, callback.from_user.id):
        await callback.answer("Подтверждение доступно только в личном чате.", show_alert=True)
        return
    parts = (callback.data or "").split(":")
    if len(parts) != 3 or parts[1] not in {"y", "n"}:
        await callback.answer("Запрос недоступен.")
        return
    result = await approval.transition(
        redis, parts[2], "approve" if parts[1] == "y" else "deny",
        owner=callback.from_user.id,
        user=callback.from_user.model_dump(include={"id", "first_name", "last_name", "username", "language_code"}, exclude_none=True),
    )
    if result[0] not in {"approved", "denied"}:
        await callback.answer("Запрос уже обработан или истёк.", show_alert=True)
        return
    await callback.answer("Вход подтверждён" if result[0] == "approved" else "Вход отклонён")
    if result[0] == "denied":
        await callback.message.edit_text("Вход отклонён.")
        return
    payment = result[1] == "payments"
    url = settings.public_base_url.rstrip("/") + ("/login?section=payments" if payment else "/login")
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Открыть пополнение в браузере" if payment else "Открыть веб-версию", url=url)
    ]])
    await callback.message.edit_text(
        "Вход подтверждён. Вернитесь в исходную вкладку браузера — "
        + ("откроется пополнение ROX." if payment else "откроется ROXY.")
        + "\nЕсли кнопка откроет другой браузер, потребуется новый вход.",
        reply_markup=keyboard,
    )
