import httpx  # Убедись, что эта строка есть

async def listings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = 'https://prod-api.bigpump.app/api/v1/coins?sortType=listing&limit=20'
    headers = {
        'accept': '*/*',
        'origin': 'https://bigpump.app',
        'referer': 'https://bigpump.app/',
        'user-agent': 'Mozilla/5.0'
    }

    try:
        response = httpx.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        tokens = data.get("coins", [])

        if not tokens:
            await update.message.reply_text("Новых листингов не найдено.")
            return

        message_lines = ["🆕 *Последние листинги BigPump:*"]
        for i, token in enumerate(tokens, start=1):
            name = token.get("name", "???")
            symbol = token.get("symbol", "???")
            price = token.get("price_usd", 0)
            address = token.get("address", "")
            link = f"https://tonviewer.com/{address}"
            message_lines.append(f"{i}. {name} ({symbol}) — ${price:.4f} [🔍 TonViewer]({link})")

        message = "\n".join(message_lines)
        await update.message.reply_markdown(message)

    except Exception as e:
        logging.error(f"Ошибка в /listings: {e}")
        await update.message.reply_text("Ошибка при получении данных.")
