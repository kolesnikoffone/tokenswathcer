import aiohttp
from datetime import datetime, timedelta

# Получить список всех токенов
async def fetch_all_jettons():
    url = "https://api.dyor.io/v1/jettons"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            return data.get("jettons", [])

# Получить информацию о токене по адресу
async def fetch_jetton_info(address):
    url = f"https://api.dyor.io/v1/jetton/{address}/info"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status == 200:
                return await resp.json()
            return {}

# Получить топ токенов по росту цены
async def get_top_jettons(limit=10):
    jettons = await fetch_all_jettons()
    results = []
    for token in jettons:
        address = token.get("address")
        info = await fetch_jetton_info(address)
        try:
            change = float(info.get("priceChange24h", 0))
            liquidity = float(info.get("liquidity", 0))
            price = float(info.get("price", 0))
            symbol = token.get("symbol")
            name = token.get("name")
            results.append({
                "symbol": symbol,
                "name": name,
                "change": change,
                "liquidity": liquidity,
                "price": price
            })
        except:
            continue
    sorted_data = sorted(results, key=lambda x: -x["change"])
    return sorted_data[:limit]

# Форматирование текста
async def format_top_tokens():
    tokens = await get_top_jettons()
    lines = []
    for i, token in enumerate(tokens, 1):
        emoji = "🔥" if token['change'] > 10 else "📈" if token['change'] > 0 else "📉"
        line = f"{i}. {emoji} <b>{token['symbol']}</b> ({token['name']})\nИзм: {token['change']:+.2f}% | Ликвид: ${token['liquidity']:.0f}"
        lines.append(line)
    timestamp = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
    return f"<b>\ud83d\udd25 Топ за 24ч:</b>\n\n" + "\n".join(lines) + f"\n\nОбновлено: {timestamp} (UTC+3)"

# Команда /hots
async def hots_command(update, context):
    text = await format_top_tokens()
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)

# Команда /listings — просто свежие токены
async def listings_command(update, context):
    jettons = await fetch_all_jettons()
    timestamp = (datetime.utcnow() + timedelta(hours=3)).strftime("%d.%m.%Y %H:%M:%S")
    lines = []
    for j in jettons[:10]:
        name = j.get("name", "")
        symbol = j.get("symbol", "")
        lines.append(f"<b>{symbol}</b> ({name})")
    text = f"<b>\U0001f195 Новые листинги:</b>\n\n" + "\n".join(lines) + f"\n\nОбновлено: {timestamp} (UTC+3)"
    await update.message.reply_text(text, parse_mode="HTML", disable_web_page_preview=True)
