"""
handlers/payment.py — coin shop and donate handlers via CryptoPay.
"""
import asyncio
import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

from services import payment_service, cabbit_service
from services.payment_service import COIN_PACKS, DONATE_CURRENCIES

logger = logging.getLogger(__name__)

router = Router()


class DonateState(StatesGroup):
    waiting_amount = State()
    waiting_currency = State()


# ── Shop ──────────────────────────────────────────────────────────────────────

@router.message(Command("shop"))
async def cmd_shop(message: Message):
    buttons = [
        [InlineKeyboardButton(
            text=f"🪙 {p['label']} — {p['price']:.0f}$",
            callback_data=f"buy_coins:{i}",
        )]
        for i, p in enumerate(COIN_PACKS)
    ]
    await message.answer(
        "🏪 <b>Магазин монет</b>\n\n"
        "Курс: <b>100 монет = 1 USDT</b>\n"
        "Выбери пакет:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(F.data.startswith("buy_coins:"))
async def callback_buy_coins(callback: CallbackQuery):
    pack_idx = int(callback.data.split(":")[1])
    user_id = callback.from_user.id

    cab = await cabbit_service.get_cabbit(user_id)
    if not cab:
        await callback.answer("Сначала создай кеббита!", show_alert=True)
        return

    await callback.answer()
    result = await payment_service.create_coin_invoice(user_id, pack_idx)

    if not result.get("ok"):
        await callback.message.edit_text("❌ Ошибка создания платежа. Попробуй позже.")
        return

    pack = COIN_PACKS[pack_idx]
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=result["url"])],
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_pay:{result['invoice_id']}:coins:{pack['coins']}")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="pay_cancel")],
    ])

    await callback.message.edit_text(
        f"🪙 <b>Покупка {pack['coins']} монет</b>\n\n"
        f"Сумма: <b>{pack['price']:.0f} USDT</b>\n\n"
        f"Нажми «Оплатить», а после оплаты — «Я оплатил».",
        reply_markup=kb,
    )


# ── Donate ────────────────────────────────────────────────────────────────────

@router.message(Command("donate"))
async def cmd_donate(message: Message, state: FSMContext):
    await state.set_state(DonateState.waiting_amount)
    await message.answer(
        "💝 <b>Донат</b>\n\n"
        "Введи сумму (число):",
    )


@router.message(DonateState.waiting_amount)
async def donate_amount(message: Message, state: FSMContext):
    try:
        amount = float(message.text.replace(",", ".").strip())
        if amount <= 0:
            raise ValueError
    except (ValueError, AttributeError):
        await message.answer("❌ Введи корректное число. Попробуй ещё раз:")
        return

    await state.update_data(amount=amount)
    await state.set_state(DonateState.waiting_currency)

    buttons = [
        [InlineKeyboardButton(text=cur, callback_data=f"donate_cur:{cur}")]
        for cur in DONATE_CURRENCIES
    ]
    await message.answer(
        f"Сумма: <b>{amount}</b>\n\nВыбери валюту:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


@router.callback_query(DonateState.waiting_currency, F.data.startswith("donate_cur:"))
async def donate_currency(callback: CallbackQuery, state: FSMContext):
    asset = callback.data.split(":")[1]
    data = await state.get_data()
    amount = data.get("amount", 0)
    await state.clear()

    if amount <= 0:
        await callback.answer("Ошибка, попробуй заново /donate", show_alert=True)
        return

    user_id = callback.from_user.id
    await callback.answer()

    result = await payment_service.create_donate_invoice(user_id, amount, asset)
    if not result.get("ok"):
        await callback.message.edit_text(f"❌ Ошибка: {result.get('error', 'unknown')}")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Оплатить", url=result["url"])],
        [InlineKeyboardButton(text="✅ Я оплатил", callback_data=f"check_pay:{result['invoice_id']}:donate:0")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="pay_cancel")],
    ])

    await callback.message.edit_text(
        f"💝 <b>Донат</b>\n\n"
        f"Сумма: <b>{amount} {asset}</b>\n\n"
        f"Нажми «Оплатить», а после оплаты — «Я оплатил».",
        reply_markup=kb,
    )


# ── Payment check ─────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("check_pay:"))
async def callback_check_pay(callback: CallbackQuery):
    parts = callback.data.split(":")
    invoice_id = int(parts[1])
    pay_type = parts[2]
    coins = int(parts[3])

    invoice = await payment_service.check_invoice(invoice_id)
    if not invoice:
        await callback.answer("❌ Не удалось проверить платёж.", show_alert=True)
        return

    if invoice["status"] == "paid":
        await callback.answer()
        user_id = callback.from_user.id

        if pay_type == "coins" and coins > 0:
            result = await cabbit_service.add_coins(user_id, coins)
            if result.get("ok"):
                await callback.message.edit_text(
                    f"✅ <b>Оплата получена!</b>\n\n"
                    f"🪙 +{coins} монет зачислено.\n"
                    f"Баланс: <b>{result['cabbit']['coins']}</b> монет"
                )
            else:
                await callback.message.edit_text(
                    f"✅ Оплата получена, но ошибка начисления. Напиши админу."
                )
        else:
            await callback.message.edit_text(
                f"✅ <b>Спасибо за донат!</b>\n\n"
                f"💝 {invoice['amount']} {invoice['asset']} получено.\n"
                f"Мы ценим твою поддержку!"
            )
    elif invoice["status"] == "active":
        await callback.answer("⏳ Платёж ещё не получен. Оплати и попробуй снова.", show_alert=True)
    elif invoice["status"] == "expired":
        await callback.answer()
        await callback.message.edit_text("❌ Время на оплату истекло. Попробуй заново.")
    else:
        await callback.answer("❌ Платёж отменён.", show_alert=True)


@router.callback_query(F.data == "pay_cancel")
async def callback_pay_cancel(callback: CallbackQuery):
    await callback.answer()
    await callback.message.edit_text("❌ Платёж отменён.")
