"""
services/payment_service.py — CryptoPay integration for coin purchases and donations.
"""
import asyncio
import logging

from aiocryptopay import AioCryptoPay, Networks
from config import CRYPTOPAY_TOKEN, CRYPTOPAY_TESTNET

logger = logging.getLogger(__name__)

COINS_PER_DOLLAR = 100

COIN_PACKS = [
    {"coins": 100, "price": 1.0, "label": "100 монет"},
    {"coins": 500, "price": 5.0, "label": "500 монет"},
    {"coins": 1000, "price": 10.0, "label": "1000 монет"},
    {"coins": 5000, "price": 50.0, "label": "5000 монет"},
]

DONATE_CURRENCIES = ["USDT", "TON", "BTC", "ETH", "LTC", "BNB", "TRX"]

_crypto: AioCryptoPay | None = None


def get_crypto() -> AioCryptoPay:
    global _crypto
    if _crypto is None:
        network = Networks.TEST_NET if CRYPTOPAY_TESTNET else Networks.MAIN_NET
        _crypto = AioCryptoPay(token=CRYPTOPAY_TOKEN, network=network)
    return _crypto


async def create_coin_invoice(user_id: int, pack_index: int) -> dict:
    if pack_index < 0 or pack_index >= len(COIN_PACKS):
        return {"ok": False, "error": "invalid_pack"}

    pack = COIN_PACKS[pack_index]
    crypto = get_crypto()

    try:
        invoice = await crypto.create_invoice(
            asset="USDT",
            amount=pack["price"],
            description=f"Покупка {pack['coins']} монет для Cabbit",
            payload=f"coins:{user_id}:{pack['coins']}",
            expires_in=1800,
        )
        return {
            "ok": True,
            "invoice_id": invoice.invoice_id,
            "url": invoice.mini_app_invoice_url,
            "coins": pack["coins"],
            "price": pack["price"],
        }
    except Exception as e:
        logger.error(f"create_coin_invoice error: {e}")
        return {"ok": False, "error": str(e)}


async def create_donate_invoice(user_id: int, amount: float, asset: str) -> dict:
    if asset not in DONATE_CURRENCIES:
        return {"ok": False, "error": "invalid_currency"}
    if amount <= 0:
        return {"ok": False, "error": "invalid_amount"}

    crypto = get_crypto()

    try:
        invoice = await crypto.create_invoice(
            asset=asset,
            amount=amount,
            description="Донат для Cabbit",
            payload=f"donate:{user_id}:{amount}:{asset}",
            expires_in=1800,
        )
        return {
            "ok": True,
            "invoice_id": invoice.invoice_id,
            "url": invoice.mini_app_invoice_url,
            "amount": amount,
            "asset": asset,
        }
    except Exception as e:
        logger.error(f"create_donate_invoice error: {e}")
        return {"ok": False, "error": str(e)}


async def check_invoice(invoice_id: int) -> dict | None:
    crypto = get_crypto()
    try:
        invoices = await crypto.get_invoices(invoice_ids=invoice_id)
        if invoices:
            inv = invoices[0]
            return {
                "invoice_id": inv.invoice_id,
                "status": inv.status,
                "amount": float(inv.amount),
                "asset": inv.asset,
                "payload": inv.payload or "",
            }
    except Exception as e:
        logger.error(f"check_invoice error: {e}")
    return None
