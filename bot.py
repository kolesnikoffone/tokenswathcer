import asyncio
import logging
import os
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

API_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BIGPUMP_API_URL = 'https://prod-api.bigpump.app/api/v1/coins/list?limit=150&sort=liq_mcap&order=desc'
TON_API_URL = 'https://api.ton.sh/rates'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

separator = '—' * 35

async def fetch_bigpump_data():
    headers = {
        "accept": "*/*",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "origin": "https://bigpump.app",
        "priority": "u=1, i",
        "referer": "https://bigpump.app/",
        "sec-ch-ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
        "sec-ch-ua-mobile": "?1",
        "sec-ch-ua-platform": '"Android"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "telegramrawdata": "query_id=AAEaYrUMAAAAABpitQwu6gcp&user=%7B%22id%22%3A213213722%2C%22first_name%22%3A%22Igor%22%2C%22last_name%22%3A%22Koles%22%2C%22username%22%3A%22kolesnikoffone%22%2C%22language_code%22%3A%22en%22%2C%22is_premium%22%3Atrue%2C%22allows_write_to_pm%22%3Atrue%2C%22photo_url%22%3A%22https%3A%5C%2F%5C%2Ft.me%5C%2Fi%5C%2Fuserpic%5C%2F320%5C%2FLOS2-JjhnhmjzAqoRwJhBdgkfv48pIMkDeo8El8OkCc.svg%22%7D&auth_date=1739471509&signature=_BACnt92QPix6-bfrlGuo5HiA4XBiSI6BP-v3jQRUVJqp2N8ydUMmWGixj4e9s9x0o0xONFOa51eo2W1JfbYBQ&hash=0c3fd36bf663249d93da37b949087c716d9e883171da0fa107f026bf439bd9d3",
        "user-agent": "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Mobile Safari/537.36"
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(BIGPUMP_API_URL, headers=headers)
        response.raise_for_status()
        return response.json()

async def fetch_ton_price():
    async with httpx.AsyncClient() as client:
        response = await client.get(TON_API_URL)
        response.raise_for_status()
        data = response.json()
        return float(data["rates"]["TON"]["prices"]["USD"])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Напиши /tokens чтобы увидеть топ токены.")

async def tokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_tokens(update.effective_chat.id, context)

async def refresh_tokens(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await send_tokens(query.message.chat.id, context, query.message.message_id)

async def send_tokens(chat_id, context: ContextTypes.DEFAULT_TYPE, message_id=None):
    try:
        bigpump_data = await fetch_bigpump_data()
        ton_price = await fetch_ton_price()
        tokens = bigpump_data.get("items", [])

        filtered_tokens = [
            token for token in tokens
            if token.get("marketCap") and (float(token["marketCap"]) / 10**9 * ton_price) >= 11000
        ]

        filtered_tokens = filtered_tokens[:30]

        result = []
        for idx, token in enumerate(filtered_tokens, start=1):
            name = token.get("name", "N/A")
            symbol = token.get("symbol", "N/A")
            address = token.get("address", "")
            mcap_value = token.get("marketCap")
            growth = token.get("priceChange1H", "N/A")

            if mcap_value:
                mcap = float(mcap_value) / 10**9 * ton_price
                mcap_str = f"<b>${mcap/1000:.1f}K</b>"
            else:
                mcap_str = "N/A"

            ref_address = address.replace(":", "")
            name_symbol = f"<a href='https://t.me/tontrade?start=prghZZEt-{ref_address}'>{name} ({symbol})</a>"

            emoji = ""
            if growth != "N/A":
                try:
                    growth_value = float(growth)
                    if growth_value >= 100:
                        emoji = "💎"
                    elif growth_value >= 50:
                        emoji = "🤑"
                    elif growth_value >= 25:
                        emoji = "💸"
                    elif growth_value >= 10:
                        emoji = "💪"
                    elif growth_value >= 5:
                        emoji = "🙃"
                    elif growth_value > 0:
                        emoji = "🥹"
                    elif growth_value > -10:
                        emoji = "🥲"
                    elif growth_value > -25:
                        emoji = "😭"
                    else:
                        emoji = "🤡"
                except ValueError:
                    pass

            growth_str = f"{emoji} {growth}%" if growth != "N/A" else "N/A"

            line = f"{idx}. {name_symbol} | {mcap_str} | {growth_str}\n{separator}"
            result.append(line)

        if result and result[-1].endswith(separator):
            result[-1] = result[-1].rsplit("\n", 1)[0]

        final_text = "\n".join(result[:15])

        markup = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔄 Обновить", callback_data="refresh_tokens")]]
        )

        if message_id:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=final_text, reply_markup=markup, parse_mode='HTML', disable_web_page_preview=True)
        else:
            await context.bot.send_message(chat_id=chat_id, text=final_text, reply_markup=markup, parse_mode='HTML', disable_web_page_preview=True)

    except Exception as e:
        logger.error(f"Ошибка при получении токенов: {e}")

if __name__ == "__main__":
    import asyncio
    from telegram.ext import ApplicationBuilder

    app = ApplicationBuilder().token(API_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("tokens", tokens))
    app.add_handler(CallbackQueryHandler(refresh_tokens, pattern="refresh_tokens"))

    app.run_polling()
