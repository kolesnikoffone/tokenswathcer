import logging
import os
import aiohttp
import base64
import crcmod
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
latest_tokens_result = None

async def get_ton_price():
    url = 'https://api.coingecko.com/api/v3/simple/price?ids=the-open-network&vs_currencies=usd'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return float(data["the-open-network"]["usd"])
    except Exception as e:
        logger.warning(f"Не удалось получить цену TON: {e}")
    return 0

async def get_tokens():
    url = 'https://api.dyor.io/v1/jettons?sort=createdAt&order=desc&limit=30&excludeScam=true'
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                logger.info(f"DYOR API responded with status {response.status}")
                if response.status == 200:
                    data = await response.json()
                    tokens = data.get('jettons', [])
                    address_book = data.get('addressBook', {})
                    logger.info(f"Получено токенов: {len(tokens)}")
                    ton_usd_price = await get_ton_price()
                    result = []

                    filtered = []
                    for token in tokens:
                        try:
                            cap = float(token.get("fdmc", {}).get("value", 0)) / (10 ** token.get("fdmc", {}).get("decimals", 6))
                            if cap >= 11:  # тысяч долларов
                                filtered.append((token, cap))
                        except:
                            continue

                    for idx, (token, cap) in enumerate(filtered[:15], 1):
                        meta = token.get('metadata', {})
                        name = meta.get('name', 'N/A')
                        symbol = meta.get('symbol', 'N/A')
                        address = meta.get('address')
                        change = token.get('priceChange1h')

                        mcap = f"<b>${cap/1000:.1f}K</b>" if cap >= 1_000 else f"<b>${cap:.2f}</b>"

                        if address and address in address_book:
                            user_friendly = address_book[address].get('userFriendly')
                            link = f"https://t.me/tontrade?start={REFERRAL_PREFIX}{user_friendly}"
                            name_symbol = f'<a href="{link}">{name} ({symbol})</a>'
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

                        line = f"{idx}. {name_symbol} | {mcap} | {growth_str}"
                        result.append(line)

                    return "\n\n".join(result) if result else "Нет подходящих токенов"
                else:
                    return f"Ошибка {response.status}"
    except Exception as e:
        logger.exception("Ошибка при обращении к DYOR API")
        return f"Ошибка при запросе: {str(e)}"

async def listings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_tokens_result
    result = await get_tokens()
    if result:
        latest_tokens_result = result
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Обновить", callback_data="refresh")]
        ])
        await update.message.reply_text(result, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=keyboard)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global latest_tokens_result
    query = update.callback_query
    await query.answer()
    result = await get_tokens()
    if result and result != latest_tokens_result:
        latest_tokens_result = result
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Обновить", callback_data="refresh")]
        ])
        try:
            await query.edit_message_text(text=result, parse_mode=ParseMode.HTML, disable_web_page_preview=True, reply_markup=keyboard)
        except Exception as e:
            logger.warning(f"Не удалось обновить сообщение: {e}")

async def tonprice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    price = await get_ton_price()
    if price:
        await update.message.reply_text(f"Текущая цена TON: <b>${price:.4f}</b>", parse_mode=ParseMode.HTML)
    else:
        await update.message.reply_text("Не удалось получить цену TON.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("listings", listings_command))
    app.add_handler(CommandHandler("tonprice", tonprice_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("Бот запущен...")
    app.run_polling()
