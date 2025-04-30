import logging
import os
import aiohttp
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
latest_tokens_raw = []
TOKENS_PER_PAGE = 10


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
    url = 'https://prod-api.bigpump.app/api/v1/coins?sortType=pocketfi&limit=30'
    headers = {
        'accept': '*/*',
        'authorization': 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJhZGRyZXNzIjoiMDpmNWI5MWRkZDBiOWM4N2VmNjUwMTFhNzlmMWRhNzE5NzIwYzVhODgwN2I1NGMxYTQwNTIyNzRmYTllMzc5YmNkIiwibmV0d29yayI6Ii0yMzkiLCJpYXQiOjE3NDI4MDY4NTMsImV4cCI6MTc3NDM2NDQ1M30.U_GaaX5psI572w4YmwAjlh8u4uFBVHdsD-zJacvWiPo'
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

                    result = []
                    for token, cap in filtered:
                        name = token.get('name', 'N/A')
                        symbol = token.get('symbol', 'N/A')
                        address = token.get('address')
                        change = token.get('priceChange1H')

                        mcap = f"<b>${cap/1000:.1f}K</b>" if cap >= 1_000 else f"<b>${cap:.2f}</b>"

                        if address:
                            try:
                                encoded_address = address_to_base64url(address)
                                logger.info(f"Address conversion: {address} -> {encoded_address}")
                                link = f"https://t.me/tontrade?start={REFERRAL_PREFIX}{encoded_address}"
                                name_symbol = f'<a href="{link}">{name} ({symbol})</a>'
                            except Exception as e:
                                logger.warning(f"Ошибка при конвертации адреса: {e}")
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

                        result.append(f"{name_symbol} | {mcap} | {growth_str}")

                    return result
    except Exception as e:
        logger.exception("Ошибка при обращении к BigPump API")
        return None


def render_tokens_page(tokens: list[str], page: int) -> tuple[str, InlineKeyboardMarkup]:
    total_pages = max(1, (len(tokens) + TOKENS_PER_PAGE - 1) // TOKENS_PER_PAGE)
    start = (page - 1) * TOKENS_PER_PAGE
    end = start + TOKENS_PER_PAGE
    lines = tokens[start:end]
    text = f"☘ <b>Листинги {page} из {total_pages}</b>\n\n" + "\n\n".join(f"{i + 1}. {line}" for i, line in enumerate(lines, start=start))
    buttons = [
        InlineKeyboardButton("⏪", callback_data=f"page:{max(1, page - 1)}"),
        InlineKeyboardButton("🔄 Обновить", callback_data="refresh"),
        InlineKeyboardButton("⏩", callback_data=f"page:{min(total_pages, page + 1)}")
    ]
    return text, InlineKeyboardMarkup([buttons])


async def listings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_tokens_raw
    raw = await get_tokens()
    if raw:
        latest_tokens_raw = raw

    if not latest_tokens_raw:
        await update.message.reply_text("Нет подходящих токенов")
        return

    text, markup = render_tokens_page(latest_tokens_raw, 1)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_tokens_raw
    query = update.callback_query
    await query.answer()

    if query.data == "refresh":
        raw = await get_tokens()
        if raw and raw != latest_tokens_raw:
            latest_tokens_raw = raw
        if not latest_tokens_raw:
            await query.edit_message_text("Нет подходящих токенов")
            return
        text, markup = render_tokens_page(latest_tokens_raw, 1)
        await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)

    elif query.data.startswith("page:"):
        page = int(query.data.split(":")[1])
        if not latest_tokens_raw:
            await query.edit_message_text("Нет подходящих токенов")
            return
        text, markup = render_tokens_page(latest_tokens_raw, page)
        try:
            await query.edit_message_text(text=text, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=markup)
        except Exception as e:
            logger.warning(f"Ошибка при обновлении страницы: {e}")


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

        message = (
            f"{emoji} <b>TON:</b> ${price:.4f} ({change:+.2f}%)\n"
            f'<a href="https://www.coingecko.com/en/coins/the-open-network">🌐 Смотреть на CoinGecko</a>'
        )
    else:
        message = "Не удалось получить цену TON 😕"

    await update.message.reply_text(message, parse_mode=ParseMode.HTML, disable_web_page_preview=False)


if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("listings", listings_command))
    app.add_handler(CommandHandler("tonprice", tonprice_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("Бот запущен...")
    app.run_polling()
