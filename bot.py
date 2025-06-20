import logging
import os
import aiohttp
from pytoniq_core import Address
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, JobQueue
from datetime import datetime, timedelta

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения TELEGRAM_BOT_TOKEN не установлена")

IGNORE_LIST_URL = "https://raw.githubusercontent.com/kolesnikoffone/savefiles/refs/heads/main/ignore_list.txt"
ignore_set = set()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

REFERRAL_PREFIX = "213213722_"
latest_hots_result = {"page": "", "timestamp": "", "ton_price": ""}
latest_bighots_result = {"page": "", "timestamp": "", "ton_price": ""}
pinned_hots_messages = {}
pinned_bighots_messages = {}

def address_to_base64url(address: str) -> str:
    return Address(address).to_str(
        is_user_friendly=True,
        is_bounceable=True,
        is_test_only=False,
        is_url_safe=True
    )

async def update_ignore_list():
    global ignore_set
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(IGNORE_LIST_URL) as response:
                if response.status == 200:
                    text = await response.text()
                    ignore_set = set(line.strip() for line in text.splitlines() if line.strip())
                    logger.info(f"🎯 Загружено игнорируемых адресов: {len(ignore_set)}")
    except Exception as e:
        logger.warning(f"⚠️ Не удалось обновить ignore list: {e}")

async def fetch_ton_price():
    url = "https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                price = data.get("price", "")
                return f"{float(price):.2f}" if price else ""
    except Exception as e:
        logger.warning(f"⚠️ Не удалось получить цену TON с Binance: {e}")
        return ""

async def fetch_tokens(min_cap: float, max_cap: float):
    await update_ignore_list()
    ton_price = await fetch_ton_price()

    url = 'https://mempad-domain.blum.codes/api/v1/jetton/sections/hot?published=include&source=all'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                data = await response.json()
                tokens = data.get("jettons", [])
                filtered = []
                for token in tokens:
                    try:
                        raw_address = token.get("address") or token.get("masterContractAddress")
                        if not raw_address:
                            continue

                        try:
                            normalized_address = Address(raw_address).to_str(
                                is_user_friendly=True,
                                is_bounceable=True,
                                is_test_only=False,
                                is_url_safe=True
                            )
                        except Exception:
                            continue

                        if normalized_address in ignore_set:
                            continue

                        change = float(token.get("stats", {}).get("price24hChange", 0))
                        cap = float(token.get("stats", {}).get("marketCap", 0))
                        volume = float(token.get("stats", {}).get("volume", 0))
                        if abs(change) < 2 or volume < 3800:
                            continue
                        if min_cap <= cap <= max_cap:
                            filtered.append((token, cap))
                    except:
                        continue
                result = []
                for idx, (token, cap) in enumerate(filtered[:10], 1):
                    name = token.get("name", "N/A")
                    symbol = token.get("ticker", "")
                    change = float(token.get("stats", {}).get("price24hChange", 0))
                    address = token.get("address") or token.get("masterContractAddress")

                    try:
                        address = Address(address).to_str(
                            is_user_friendly=True,
                            is_bounceable=True,
                            is_test_only=False,
                            is_url_safe=True
                        )
                    except Exception:
                        pass

                    mcap = f"${cap/1e6:.1f}M" if cap >= 1_000_000 else f"${cap/1e3:.1f}K"

                    try:
                        encoded_address = address_to_base64url(address)
                        link = f"https://t.me/dtrade?start={REFERRAL_PREFIX}{encoded_address}"
                        name_symbol = f'<a href="{link}">{symbol}</a>'
                    except:
                        name_symbol = f'{symbol}'

                    emoji = "💎" if change >= 100 else "🤑" if change >= 50 else "🚀" if change >= 25 else "💸" if change >= 10 else "📈" if change >= 5 else "🥹" if change > 0 else "🫥" if change > -1 else "📉" if change > -5 else "💔" if change > -10 else "😭" if change > -25 else "🤡"
                    growth_str = f"{emoji} {change:+.2f}%"
                    line = f"├{growth_str} • {name_symbol} • {mcap}"
                    result.append(line)

                timestamp = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
                return "\n".join(result), timestamp, ton_price
    except Exception as e:
        logger.error(f"Ошибка получения токенов: {e}")
        return "", "", ton_price

async def send_hots(update: Update, context: ContextTypes.DEFAULT_TYPE, min_cap: float, max_cap: float, store: dict, pinned_store: dict, tag: str):
    chat_id = update.effective_chat.id
    old_msg_id = pinned_store.get(chat_id)
    if old_msg_id:
        try:
            await context.bot.unpin_chat_message(chat_id=chat_id, message_id=old_msg_id)
            await context.bot.delete_message(chat_id=chat_id, message_id=old_msg_id)
        except Exception as e:
            logger.warning(f"Не удалось удалить старое сообщение {tag}: {e}")

    page, timestamp, ton_price = await fetch_tokens(min_cap, max_cap)
    if not page:
        return

    store["page"] = page
    store["timestamp"] = timestamp
    store["ton_price"] = ton_price
    ton_line = f"TON: ${ton_price}" if ton_price else ""
    message = f"{page}\n\n{ton_line}\n{timestamp}" if ton_line else f"{page}\n\n{timestamp}"
    sent = await update.message.reply_text(message, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    await context.bot.pin_chat_message(chat_id=chat_id, message_id=sent.message_id)
    pinned_store[chat_id] = sent.message_id

async def hots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_hots(update, context, 3_500, 100_000, latest_hots_result, pinned_hots_messages, "hots")

async def bighots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_hots(update, context, 100_000, 10_000_000, latest_bighots_result, pinned_bighots_messages, "bighots")

async def auto_update(context: ContextTypes.DEFAULT_TYPE, min_cap: float, max_cap: float, store: dict, pinned_store: dict, tag: str):
    page, timestamp, ton_price = await fetch_tokens(min_cap, max_cap)
    if not page:
        return
    store["page"] = page
    store["timestamp"] = timestamp
    store["ton_price"] = ton_price
    ton_line = f"TON: ${ton_price}" if ton_price else ""
    message = f"{page}\n\n{ton_line}\n{timestamp}" if ton_line else f"{page}\n\n{timestamp}"
    for chat_id, message_id in pinned_store.items():
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=message, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception as e:
            logger.warning(f"Не удалось обновить сообщение {tag} в чате {chat_id}: {e}")

async def auto_update_hots(context: ContextTypes.DEFAULT_TYPE):
    await auto_update(context, 3_500, 100_000, latest_hots_result, pinned_hots_messages, "hots")

async def auto_update_bighots(context: ContextTypes.DEFAULT_TYPE):
    await auto_update(context, 100_000, 10_000_000, latest_bighots_result, pinned_bighots_messages, "bighots")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("hots", hots_command))
    app.add_handler(CommandHandler("bighots", bighots_command))
    app.job_queue.run_repeating(auto_update_hots, interval=20, first=20)
    app.job_queue.run_repeating(auto_update_bighots, interval=20, first=25)
    print("Бот запущен...")
    app.run_polling()
