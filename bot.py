import logging
import os
import aiohttp
from datetime import datetime, timedelta
from pytoniq_core import Address
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения TELEGRAM_BOT_TOKEN не установлена")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

REFERRAL_PREFIX = "prghZZEt-"
latest_tokens_result = {}
PAGE_SIZE = 10


def address_to_base64url(address: str) -> str:
    return Address(address).to_str(
        is_user_friendly=True,
        is_bounceable=True,
        is_test_only=False,
        is_url_safe=True
    )


async def get_ton_price():
    url = 'https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd&include_24hr_change=true'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    price = float(data["the-open-network"]["usd"])
                    change = float(data["the-open-network"].get("usd_24h_change", 0))
                    return price, change
    except Exception as e:
        logger.warning(f"Не удалось получить цену TON: {e}")
    return None, 0


async def get_tokens():
    url = 'https://prod-api.bigpump.app/api/v1/coins?sortType=pocketfi&limit=40'
    headers = {
        'accept': '*/*',
        'accept-language': 'en-US,en;q=0.9,ru-RU;q=0.8,ru;q=0.7',
        'authorization': 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJhZGRyZXNzIjoiMDpmNWI5MWRkZDBiOWM4N2VmNjUwMTFhNzlmMWRhNzE5NzIwYzVhODgwN2I1NGMxYTQwNTIyNzRmYTllMzc5YmNkIiwibmV0d29yayI6Ii0yMzkiLCJpYXQiOjE3NDI4MDY4NTMsImV4cCI6MTc3NDM2NDQ1M30.U_GaaX5psI572w4YmwAjlh8u4uFBVHdsD-zJacvWiPo',
        'origin': 'https://bigpump.app',
        'referer': 'https://bigpump.app/',
        'user-agent': 'Mozilla/5.0'
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                logger.info(f"BigPump API responded with status {response.status}")
                if response.status == 200:
                    data = await response.json()
                    tokens = data.get('coins', [])
                    ton_usd_price, _ = await get_ton_price()

                    filtered = []
                    for token in tokens:
                        try:
                            cap = float(token.get("marketCap", 0)) * ton_usd_price / 1e9
                            if cap >= 11000:
                                filtered.append((token, cap))
                        except:
                            continue
                    return filtered
                else:
                    return []
    except Exception as e:
        logger.exception("Ошибка при обращении к BigPump API")
        return []


def format_tokens(tokens, page):
    start = (page - 1) * PAGE_SIZE
    end = start + PAGE_SIZE
    result = []
    for idx, (token, cap) in enumerate(tokens[start:end], start + 1):
        name = token.get('name', 'N/A')
        symbol = token.get('symbol', 'N/A')
        address = token.get('address')
        change = token.get('priceChange1H')

        mcap = f"<b>${cap/1000:.1f}K</b>" if cap >= 1_000 else f"<b>${cap:.2f}</b>"

        if address:
            try:
                encoded_address = address_to_base64url(address)
                link = f"https://t.me/tontrade?start={REFERRAL_PREFIX}{encoded_address}"
                name_symbol = f'<a href="{link}">{name} ({symbol})</a>'
            except:
                name_symbol = f'{name} ({symbol})'
        else:
            name_symbol = f'{name} ({symbol})'

        emoji = ""
        try:
            growth = float(change)
            if growth >= 100:
                emoji = "💎"
            elif growth >= 50:
                emoji = "🤑"
            elif growth >= 25:
                emoji = "💸"
            elif growth >= 10:
                emoji = "💪"
            elif growth >= 5:
                emoji = "🙃"
            elif growth > 0:
                emoji = "🥹"
            elif growth > -10:
                emoji = "🥲"
            elif growth > -25:
                emoji = "😭"
            else:
                emoji = "🤡"
            growth_str = f"{emoji} {growth:.2f}%"
        except:
            growth_str = "N/A"

        result.append(f"{idx}. {name_symbol} | {mcap} | {growth_str}")

    timestamp = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
    return f"Обновлено: {timestamp} (UTC+3) | ID: {start}\n\n" + "\n\n".join(result)


def get_keyboard(current_page, max_page):
    buttons = [
        InlineKeyboardButton("⏪", callback_data="page:1"),
        InlineKeyboardButton("🔄 Обновить", callback_data=f"refresh:{current_page}"),
        InlineKeyboardButton("⏩", callback_data=f"page:{2}" if current_page == 1 else f"page:{1}")
    ]
    return InlineKeyboardMarkup([buttons])


async def listings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tokens = await get_tokens()
    if not tokens:
        await update.message.reply_text("Нет подходящих токенов")
        return
    latest_tokens_result["data"] = tokens
    text = format_tokens(tokens, 1)
    reply_markup = get_keyboard(1, 2)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=reply_markup)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not latest_tokens_result.get("data"):
        latest_tokens_result["data"] = await get_tokens()

    tokens = latest_tokens_result["data"]
    data = query.data
    if data.startswith("refresh"):
        _, page = data.split(":")
        page = int(page)
    elif data.startswith("page"):
        _, page = data.split(":")
        page = int(page)
    else:
        page = 1

    text = format_tokens(tokens, page)
    reply_markup = get_keyboard(page, 2)
    try:
        await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=reply_markup)
    except Exception as e:
        logger.warning(f"Не удалось обновить сообщение: {e}")


if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("listings", listings_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("Бот запущен...")
    app.run_polling()
