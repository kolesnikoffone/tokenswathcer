import logging
import os
import aiohttp
from pytoniq_core import Address
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes
from datetime import datetime, timedelta

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения TELEGRAM_BOT_TOKEN не установлена")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

REFERRAL_PREFIX = "prghZZEt-"
latest_tokens_result = {"pages": [], "timestamp": "", "last_page": 0}
hots_tokens_result = {"pages": [], "timestamp": "", "last_page": 0}

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

async def get_tokens(sort_type="pocketfi"):
    url = f'https://prod-api.bigpump.app/api/v1/coins?sortType={sort_type}&limit=40'
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
                    pages = []
                    filtered = []
                    for token in tokens:
                        try:
                            cap = float(token.get("marketCap", 0)) * ton_usd_price / 1e9
                            if cap >= 11000:
                                filtered.append((token, cap))
                        except:
                            continue

                    for i in range(0, len(filtered), 10):
                        result = []
                        for idx, (token, cap) in enumerate(filtered[i:i+10], i+1):
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
                                    emoji = "🚀"
                                elif growth >= 10:
                                    emoji = "💸"
                                elif growth >= 5:
                                    emoji = "📈"
                                elif growth > 0:
                                    emoji = "🥹"
                                elif growth > -1:
                                    emoji = "0️⃣"
                                elif growth > -5:
                                    emoji = "📉"
                                elif growth > -10:
                                    emoji = "💔"
                                elif growth > -25:
                                    emoji = "😭"
                                else:
                                    emoji = "🤡"
                                growth_str = f"{emoji} {growth:.2f}%"
                            except:
                                growth_str = "0️⃣ 0.00%"

                            line = f"{idx}. {name_symbol} | {mcap} | {growth_str}"
                            result.append(line)
                        pages.append("\n\n".join(result))

                    timestamp = datetime.utcnow() + timedelta(hours=3)
                    formatted_time = timestamp.strftime("%d.%m.%Y %H:%M:%S")
                    return pages, formatted_time
                else:
                    return [f"Ошибка {response.status}"], ""
    except Exception as e:
        logger.exception("Ошибка при обращении к BigPump API")
        return [f"Ошибка при запросе: {str(e)}"], ""

async def hots_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global hots_tokens_result
    pages, timestamp = await get_tokens(sort_type="hot")
    if pages:
        hots_tokens_result = {
            "pages": pages,
            "timestamp": timestamp,
            "last_page": 0
        }
    else:
        pages = hots_tokens_result.get("pages")
        timestamp = hots_tokens_result.get("timestamp")

    page_idx = 0
    page_text = f"{pages[page_idx]}\n\nОбновлено: {timestamp} (UTC+3) | ID: {page_idx + 1}"
    buttons = [
        InlineKeyboardButton("🔄 Обновить", callback_data="refresh_hots"),
        InlineKeyboardButton("➡️", callback_data="next_hots")
    ]
    markup = InlineKeyboardMarkup([buttons])
    await update.message.reply_text(page_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)

async def hots_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global hots_tokens_result
    query = update.callback_query
    await query.answer()
    data = query.data

    if not hots_tokens_result["pages"]:
        return

    if data == "refresh_hots":
        pages, timestamp = await get_tokens(sort_type="hot")
        if pages:
            hots_tokens_result = {
                "pages": pages,
                "timestamp": timestamp,
                "last_page": 0
            }
        else:
            pages = hots_tokens_result.get("pages")
            timestamp = hots_tokens_result.get("timestamp")
        page_idx = 0
    elif data == "next_hots":
        page_idx = (hots_tokens_result["last_page"] + 1) % len(hots_tokens_result["pages"])
        hots_tokens_result["last_page"] = page_idx
        pages = hots_tokens_result["pages"]
        timestamp = hots_tokens_result["timestamp"]
    else:
        return

    page_text = f"{pages[page_idx]}\n\nОбновлено: {timestamp} (UTC+3) | ID: {page_idx + 1}"
    if len(hots_tokens_result["pages"]) > 1:
        nav_button = InlineKeyboardButton("➡️", callback_data="next_hots")
        buttons = [
            InlineKeyboardButton("🔄 Обновить", callback_data="refresh_hots"),
            nav_button
        ]
    else:
        buttons = [InlineKeyboardButton("🔄 Обновить", callback_data="refresh_hots")]

    markup = InlineKeyboardMarkup([buttons])
    try:
        await query.edit_message_text(page_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)
    except Exception as e:
        logger.warning(f"Не удалось обновить сообщение: {e}")

async def tonprice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price, change = await get_ton_price()
    if price is not None:
        if change >= 5:
            emoji = "🚀"
        elif change >= 1:
            emoji = "📈"
        elif change > 0:
            emoji = "🔼"
        elif change > -1:
            emoji = "🔽"
        elif change > -5:
            emoji = "📉"
        else:
            emoji = "💥"

        message = f"{emoji} <b>TON:</b> ${price:.4f} ({change:+.2f}%)"
    else:
        message = "Не удалось получить цену TON 😕"

    await update.message.reply_text(message, parse_mode=ParseMode.HTML, disable_web_page_preview=True)

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("tonprice", tonprice_command))
    app.add_handler(CommandHandler("hots", hots_command))
    app.add_handler(CallbackQueryHandler(hots_callback, pattern="^refresh_hots$|^next_hots$"))
    print("Бот запущен...")
    app.run_polling()
