# ФАЙЛ: bot.py (Только новые токены Ton.fun через парсинг сайта + топ 30 токенов)

import os
import logging
import aiohttp
import asyncio
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from datetime import datetime

# Загрузка переменных окружения
load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise Exception("Нет BOT_TOKEN! Проверь переменные окружения.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Глобальный кэш
announced_tokens = set()
latest_listings = "Данные ещё загружаются..."

async def fetch_tonfun_tokens():
    url = "https://ton.fun/tokens"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; TelegramBot/1.0)"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                raise Exception(f"Ошибка Ton.fun: {resp.status}")
            html = await resp.text()
            soup = BeautifulSoup(html, "html.parser")
            tokens = []
            for card in soup.select("a[href^='/token/']"):
                link = card.get("href")
                symbol = card.text.strip() or "UNKNOWN"
                if link and symbol:
                    address = link.split("/token/")[-1]
                    tokens.append({"jetton_address": address, "symbol": symbol})
            return tokens

async def fetch_stonfi_pools():
    url = "https://api.ston.fi/v1/stats/pool"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise Exception(f"Ошибка STON.fi API: {resp.status}")
            data = await resp.json()
            return data.get("stats", [])

async def update_listings(context: ContextTypes.DEFAULT_TYPE = None):
    global latest_listings, announced_tokens
    try:
        tonfun_tokens = await fetch_tonfun_tokens()
        stonfi_pools = await fetch_stonfi_pools()

        liquid_tokens = {}
        for pool in stonfi_pools:
            base = pool.get("base_address")
            quote = pool.get("quote_address")
            last_price = pool.get("last_price")
            base_symbol = pool.get("base_symbol")
            quote_symbol = pool.get("quote_symbol")
            if not last_price:
                continue

            if base:
                liquid_tokens[base] = (base_symbol, last_price, quote_symbol)
            if quote:
                try:
                    inverse_price = 1.0 / float(last_price)
                    liquid_tokens[quote] = (quote_symbol, f"{inverse_price:.9f}", base_symbol)
                except ZeroDivisionError:
                    continue

        message = "🆕 *Новые токены Ton.fun с ликвидностью:*\n"
        found = 0

        for token in tonfun_tokens:
            address = token.get("jetton_address")
            symbol = token.get("symbol")
            if not address or address in announced_tokens:
                continue
            if address in liquid_tokens:
                symbol_disp, price, unit = liquid_tokens[address]
                tonviewer_link = f"https://tonviewer.com/{address}"
                message += f"{found+1}. **{symbol}** — {price} {unit} — [Tonviewer]({tonviewer_link})\n"
                announced_tokens.add(address)
                found += 1
                if found >= 10:
                    break

        if found == 0:
            message += "\nНет новых токенов с ликвидностью."

        latest_listings = message + f"\n\n_Обновлено: {datetime.utcnow().strftime('%d.%m.%Y %H:%M UTC')}_"

        if context:
            await context.bot.send_message(chat_id=context.job.data, text=latest_listings, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Ошибка обновления листингов: {e}")

async def top30(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        tokens = await fetch_tonfun_tokens()
        message = "🆕 *Последние 30 токенов Ton.fun:*\n"
        for idx, token in enumerate(tokens[:30], start=1):
            address = token.get("jetton_address")
            symbol = token.get("symbol")
            tonviewer_link = f"https://tonviewer.com/{address}"
            message += f"{idx}. **{symbol}** — [Tonviewer]({tonviewer_link})\n"

        await update.message.reply_text(message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Ошибка в команде /top30: {e}")
        await update.message.reply_text("Ошибка при получении списка токенов.")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("👋 *Добро пожаловать!*\n\nЯ отслеживаю новые токены Ton.fun с ликвидностью на STON.fi!\n\n*Команды:*\n/newlistings — Новые токены с ликвидностью\n/top30 — Последние 30 токенов Ton.fun", parse_mode='Markdown')
    context.job_queue.run_repeating(update_listings, interval=1800, first=5, data=chat_id)

async def newlistings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(latest_listings, parse_mode='Markdown')

def main():
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("newlistings", newlistings))
    app.add_handler(CommandHandler("top30", top30))

    job_queue = app.job_queue
    job_queue.run_repeating(update_listings, interval=1800, first=5)

    app.run_polling()

if __name__ == "__main__":
    main()
