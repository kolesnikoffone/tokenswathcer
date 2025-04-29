import asyncio
import logging
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

API_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
BIGPUMP_API_URL = 'https://prod-api.bigpump.app/api/v1/coins/list?limit=150&sort=liq_mcap&order=desc'
TON_API_URL = 'https://api.ton.sh/rates'

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

separator = '—' * 35

async def fetch_bigpump_data():
    async with httpx.AsyncClient() as client:
        response = await client.get(BIGPUMP_API_URL)
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
            mcap_value = token.get("marketCap")
            growth = token.get("priceChange1H", "N/A")

            if mcap_value:
                mcap = float(mcap_value) / 10**9 * ton_price
                mcap_str = f"<b>${mcap/1000:.1f}K</b>"
            else:
                mcap_str = "N/A"

            name_symbol = f"{name} ({symbol})"

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

async def main():
    application = Application.builder().token(API_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("tokens", tokens))
    application.add_handler(CallbackQueryHandler(refresh_tokens, pattern="refresh_tokens"))

    await application.run_polling()

if __name__ == "__main__":
    asyncio.run(main())
