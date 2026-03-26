"""
handlers/feedback.py — bug reports, skin suggestions, and player reports.
Sends reports to admin via a separate notification bot.
"""
import logging

from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup,
    BufferedInputFile,
)
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from config import ADMIN_ID, NOTIFY_BOT_TOKEN

logger = logging.getLogger(__name__)

router = Router()

_notify_bot: Bot | None = None


def _get_notify_bot() -> Bot | None:
    global _notify_bot
    if not NOTIFY_BOT_TOKEN:
        return None
    if _notify_bot is None:
        _notify_bot = Bot(token=NOTIFY_BOT_TOKEN)
    return _notify_bot


async def _send_photo_via_notify(main_bot: Bot, file_id: str, caption: str):
    """Download photo from main bot and send via notify bot."""
    notify = _get_notify_bot()
    if not notify:
        return
    file = await main_bot.get_file(file_id)
    photo_bytes = await main_bot.download_file(file.file_path)
    input_file = BufferedInputFile(photo_bytes.read(), filename="evidence.jpg")
    await notify.send_photo(chat_id=ADMIN_ID, photo=input_file, caption=caption)


class IdeaState(StatesGroup):
    waiting_description = State()


class BugState(StatesGroup):
    waiting_description = State()


class SkinSuggestState(StatesGroup):
    waiting_name = State()
    waiting_photo = State()


class ReportState(StatesGroup):
    waiting_name = State()
    waiting_description = State()
    waiting_evidence = State()


FEEDBACK_TEXT = "📬 <b>Обратная связь</b>\n\nВыбери действие:"
FEEDBACK_KB = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="🐛 Сообщить о баге", callback_data="fb:bug")],
    [InlineKeyboardButton(text="🎨 Предложить скин", callback_data="fb:skin")],
    [InlineKeyboardButton(text="💡 Предложить идею", callback_data="fb:idea")],
    [InlineKeyboardButton(text="🚨 Жалоба на игрока", callback_data="fb:report")],
])


# ── Menu ──────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "fb:menu")
async def callback_fb_menu(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer()
    await callback.message.edit_text(FEEDBACK_TEXT, reply_markup=FEEDBACK_KB)


# ── Bug report ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "fb:bug")
async def callback_fb_bug(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(BugState.waiting_description)
    await callback.message.edit_text(
        "🐛 <b>Баг-репорт</b>\n\n"
        "Опиши баг подробно (текстом):"
    )


@router.message(BugState.waiting_description, F.text)
async def bug_description(message: Message, state: FSMContext):
    await state.clear()
    text = message.text.strip()
    if not text:
        await message.answer("❌ Описание не может быть пустым.")
        return

    user = message.from_user
    report = (
        f"#баг\n\n"
        f"👤 {user.full_name} (ID: {user.id})\n"
        f"@{user.username}\n\n"
        f"📝 {text}"
    )

    bot = _get_notify_bot()
    if bot:
        try:
            await bot.send_message(chat_id=ADMIN_ID, text=report)
        except Exception as e:
            logger.error(f"bug notify error: {e}")

    await message.answer(
        "✅ <b>Баг-репорт отправлен!</b>\n\n"
        "Спасибо, мы разберёмся. "
        "Если баг подтвердится — получишь вознаграждение!"
    )


@router.message(BugState.waiting_description)
async def bug_not_text(message: Message):
    await message.answer("❌ Отправь описание бага текстом. Или /cancel для отмены.")


# ── Idea suggestion ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "fb:idea")
async def callback_fb_idea(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(IdeaState.waiting_description)
    await callback.message.edit_text(
        "💡 <b>Предложить идею</b>\n\n"
        "Опиши свою идею (текстом):"
    )


@router.message(IdeaState.waiting_description, F.text)
async def idea_description(message: Message, state: FSMContext):
    await state.clear()
    text = message.text.strip()
    if not text:
        await message.answer("❌ Описание не может быть пустым.")
        return

    user = message.from_user
    report = (
        f"#идея\n\n"
        f"👤 {user.full_name} (ID: {user.id})\n"
        f"@{user.username}\n\n"
        f"💡 {text}"
    )

    bot = _get_notify_bot()
    if bot:
        try:
            await bot.send_message(chat_id=ADMIN_ID, text=report)
        except Exception as e:
            logger.error(f"idea notify error: {e}")

    await message.answer(
        "✅ <b>Идея отправлена!</b>\n\n"
        "Спасибо за предложение!"
    )


@router.message(IdeaState.waiting_description)
async def idea_not_text(message: Message):
    await message.answer("❌ Опиши идею текстом. Или /cancel для отмены.")


# ── Skin suggestion ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "fb:skin")
async def callback_fb_skin(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await state.set_state(SkinSuggestState.waiting_name)
    await callback.message.edit_text(
        "🎨 <b>Предложить скин</b>\n\n"
        "Введи название скина:"
    )


@router.message(SkinSuggestState.waiting_name, F.text)
async def suggestskin_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("❌ Название не может быть пустым.")
        return

    await state.update_data(skin_name=name)
    await state.set_state(SkinSuggestState.waiting_photo)
    await message.answer(
        f"🎨 Скин: <b>{name}</b>\n\n"
        "Теперь отправь картинку со скином:"
    )


@router.message(SkinSuggestState.waiting_name)
async def suggestskin_name_not_text(message: Message):
    await message.answer("❌ Отправь название текстом. Или /cancel для отмены.")


@router.message(SkinSuggestState.waiting_photo, F.photo)
async def suggestskin_photo(message: Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    skin_name = data.get("skin_name", "Без названия")
    user = message.from_user

    caption = (
        f"#скин\n\n"
        f"👤 {user.full_name} (ID: {user.id})\n"
        f"@{user.username}\n\n"
        f"🎨 Название: {skin_name}"
    )

    try:
        await _send_photo_via_notify(message.bot, message.photo[-1].file_id, caption)
    except Exception as e:
        logger.error(f"suggestskin notify error: {e}")

    await message.answer(
        "✅ <b>Скин отправлен на рассмотрение!</b>\n\n"
        "Если скин будет добавлен — мы оповестим!"
    )


@router.message(SkinSuggestState.waiting_photo)
async def suggestskin_not_photo(message: Message):
    await message.answer("❌ Отправь именно фото. Или /cancel для отмены.")


# ── Player report ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "fb:report")
async def callback_fb_report(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Мультиаккаунт", callback_data="fb:report_type:мультиаккаунт")],
        [InlineKeyboardButton(text="🐛 Багоюз", callback_data="fb:report_type:багоюз")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="fb:menu")],
    ])
    await callback.message.edit_text(
        "🚨 <b>Жалоба на игрока</b>\n\n"
        "Выбери тип нарушения:",
        reply_markup=kb,
    )


@router.callback_query(F.data.startswith("fb:report_type:"))
async def callback_report_type(callback: CallbackQuery, state: FSMContext):
    report_type = callback.data.split(":", 2)[2]
    await callback.answer()
    await state.update_data(report_type=report_type)
    await state.set_state(ReportState.waiting_name)
    await callback.message.edit_text(
        f"🚨 <b>Жалоба: {report_type}</b>\n\n"
        "Введи имя нарушителя (или user_id):"
    )


@router.message(ReportState.waiting_name, F.text)
async def report_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("❌ Имя не может быть пустым.")
        return

    await state.update_data(target_name=name)
    await state.set_state(ReportState.waiting_description)
    await message.answer(
        "📝 Опиши что именно произошло:"
    )


@router.message(ReportState.waiting_name)
async def report_name_not_text(message: Message):
    await message.answer("❌ Введи имя текстом. Или /cancel для отмены.")


@router.message(ReportState.waiting_description, F.text)
async def report_description(message: Message, state: FSMContext):
    desc = message.text.strip()
    if not desc:
        await message.answer("❌ Описание не может быть пустым.")
        return

    await state.update_data(description=desc)
    await state.set_state(ReportState.waiting_evidence)
    await message.answer(
        "📎 Приложи скриншот-доказательство (фото).\n\n"
        "Если доказательств нет — отправь «нет» текстом.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏭ Отправить без скрина", callback_data="fb:report_skip_evidence")],
        ]),
    )


@router.message(ReportState.waiting_description)
async def report_desc_not_text(message: Message):
    await message.answer("❌ Опиши нарушение текстом. Или /cancel для отмены.")


@router.callback_query(ReportState.waiting_evidence, F.data == "fb:report_skip_evidence")
async def report_skip_evidence(callback: CallbackQuery, state: FSMContext):
    await callback.answer()
    await _send_report(callback.from_user, state, main_bot=callback.bot)
    await callback.message.edit_text(
        "✅ <b>Жалоба отправлена!</b>\n\n"
        "Администрация рассмотрит её в ближайшее время.\n"
        "⚠️ Ложные жалобы могут привести к бану."
    )


@router.message(ReportState.waiting_evidence, F.photo)
async def report_with_evidence(message: Message, state: FSMContext):
    await state.update_data(evidence_file_id=message.photo[-1].file_id)
    await _send_report(message.from_user, state, main_bot=message.bot)
    await message.answer(
        "✅ <b>Жалоба отправлена!</b>\n\n"
        "Администрация рассмотрит её в ближайшее время.\n"
        "⚠️ Ложные жалобы могут привести к бану."
    )


@router.message(ReportState.waiting_evidence, F.text)
async def report_text_no_evidence(message: Message, state: FSMContext):
    if message.text.strip().lower() in ("нет", "no", "skip", "-"):
        await _send_report(message.from_user, state, main_bot=message.bot)
        await message.answer(
            "✅ <b>Жалоба отправлена!</b>\n\n"
            "Администрация рассмотрит её в ближайшее время.\n"
            "⚠️ Ложные жалобы могут привести к бану."
        )
        return
    await message.answer("❌ Отправь скриншот (фото) или напиши «нет».")


@router.message(ReportState.waiting_evidence)
async def report_evidence_wrong(message: Message):
    await message.answer("❌ Отправь скриншот (фото) или напиши «нет». Или /cancel для отмены.")


async def _send_report(user, state: FSMContext, main_bot: Bot):
    data = await state.get_data()
    await state.clear()

    report_type = data.get("report_type", "?")
    target_name = data.get("target_name", "?")
    description = data.get("description", "?")
    evidence_file_id = data.get("evidence_file_id")

    text = (
        f"#жалоба #{report_type.replace(' ', '_')}\n\n"
        f"👤 От: {user.full_name} (ID: {user.id}) @{user.username}\n"
        f"🎯 На: {target_name}\n"
        f"📋 Тип: {report_type}\n\n"
        f"📝 {description}"
    )

    notify = _get_notify_bot()
    if not notify:
        return

    try:
        if evidence_file_id:
            await _send_photo_via_notify(main_bot, evidence_file_id, text)
        else:
            await notify.send_message(chat_id=ADMIN_ID, text=text + "\n\n📎 Без доказательств")
    except Exception as e:
        logger.error(f"report notify error: {e}")
