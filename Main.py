import asyncio
import os
import sqlite3
import aiohttp
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SOSO_API_KEY = os.getenv("SOSO_API_KEY")

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN missing!")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()

BASE_URL = "https://openapi.sosovalue.com/openapi/v1"

COIN_MAP = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano", "DOGE": "dogecoin"
}

# Database
conn = sqlite3.connect("sosoagent.db")
cur = conn.cursor()
cur.execute("""
    CREATE TABLE IF NOT EXISTS portfolio (
        user_id INTEGER,
        coin TEXT,
        amount REAL,
        PRIMARY KEY(user_id, coin)
    )
""")
conn.commit()

# ==================== MENUS ====================

def main_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Prices", callback_data="prices")],
        [InlineKeyboardButton(text="📊 Market Summary", callback_data="market")],
        [InlineKeyboardButton(text="😨 Fear & Greed", callback_data="fear")],
        [InlineKeyboardButton(text="📰 News", callback_data="news")],
        [InlineKeyboardButton(text="📈 ETF Flows", callback_data="etf")],
        [InlineKeyboardButton(text="📈 My Portfolio", callback_data="portfolio")],
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu")]
    ])
    return keyboard

def portfolio_add_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="BTC +0.1", callback_data="addp_BTC_0.1"),
         InlineKeyboardButton(text="BTC +0.5", callback_data="addp_BTC_0.5")],
        [InlineKeyboardButton(text="ETH +0.5", callback_data="addp_ETH_0.5"),
         InlineKeyboardButton(text="ETH +2", callback_data="addp_ETH_2")],
        [InlineKeyboardButton(text="SOL +5", callback_data="addp_SOL_5"),
         InlineKeyboardButton(text="← Back", callback_data="menu")]
    ])
    return keyboard

# ==================== API HELPERS ====================

async def soso_api_call(endpoint: str, params: dict = None):
    if not SOSO_API_KEY:
        return None
    try:
        headers = {"x-soso-api-key": SOSO_API_KEY}
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{BASE_URL}{endpoint}", headers=headers, params=params, timeout=15) as resp:
                if resp.status == 200:
                    return await resp.json()
                return None
    except:
        return None

async def get_price(symbol: str):
    coin = COIN_MAP.get(symbol.upper())
    if not coin:
        return None

    data = await soso_api_call(f"/currencies/{coin}/market-snapshot")
    if data and isinstance(data, dict):
        price = data.get("data", {}).get("price") or data.get("price")
        if price:
            return float(price)

    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin}&vs_currencies=usd"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get(coin, {}).get("usd")
    except:
        pass
    return None

async def get_fear_greed():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://api.alternative.me/fng/") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    item = data["data"][0]
                    return item["value"], item["value_classification"]
    except:
        pass
    return None, None

async def get_news():
    data = await soso_api_call("/news", {"limit": 5})
    if data and isinstance(data, dict):
        items = data.get("data") or data.get("items", [])
        if items:
            return items[:3]

    try:
        url = "https://min-api.cryptocompare.com/data/v2/news/?lang=EN"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return result.get("Data", [])[:3]
    except:
        pass
    return []

async def get_etf_data():
    return await soso_api_call("/etfs/summary-history", {"limit": 5})

# ==================== HANDLERS ====================

@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 <b>Welcome to SoSoAgent Bot!</b> 🚀\n\n"
        "Tap the buttons below:",
        reply_markup=main_menu()
    )

@dp.callback_query(lambda c: c.data == "menu")
async def show_menu(callback):
    await callback.message.edit_text("<b>Main Menu</b>", reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "prices")
async def prices(callback):
    text = "<b>💰 Live Prices</b>\n\n"
    for symbol in ["BTC", "ETH", "SOL"]:
        price = await get_price(symbol)
        text += f"<b>{symbol}</b>: ${price:,.2f if price else 'N/A'}\n"
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "market")
async def market(callback):
    btc = await get_price("BTC")
    value, label = await get_fear_greed()
    text = "<b>📊 Market Summary</b>\n\n"
    if btc:
        text += f"BTC: ${btc:,.2f}\n"
    if value:
        text += f"Fear & Greed: {value} ({label})"
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "fear")
async def fear(callback):
    value, label = await get_fear_greed()
    text = f"<b>Fear & Greed</b>\n{value} — {label}" if value else "❌ Unavailable"
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "news")
async def news(callback):
    articles = await get_news()
    if articles:
        text = "<b>📰 Latest News</b>\n\n"
        for a in articles:
            title = a.get("title", "News")[:80]
            url = a.get("url", "")
            text += f"• <b>{title}</b>\n{url}\n\n"
    else:
        text = "❌ No news available."
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "etf")
async def etf(callback):
    data = await get_etf_data()
    if data:
        text = "<b>📈 ETF Flows</b>\n\n" + str(data)[:500]
    else:
        text = "📊 <b>ETF Flows</b>\n\nSoSoValue ETF data is loading..."
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "portfolio")
async def portfolio(callback):
    cur.execute("SELECT coin, amount FROM portfolio WHERE user_id=?", (callback.from_user.id,))
    rows = cur.fetchall()
    if not rows:
        text = "📭 <b>Portfolio empty</b>\n\nTap below to add holdings"
        await callback.message.edit_text(text, reply_markup=portfolio_add_menu())
    else:
        total = 0
        text = "<b>📈 My Portfolio</b>\n\n"
        for coin, amount in rows:
            price = await get_price(coin)
            if price:
                value = price * amount
                total += value
                text += f"🪙 <b>{coin}</b>\nAmount: {amount}\nValue: <b>${value:,.2f}</b>\n\n"
        text += f"💰 <b>Total: ${total:,.2f}</b>"
        await callback.message.edit_text(text, reply_markup=portfolio_add_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("addp_"))
async def add_to_portfolio(callback):
    try:
        _, coin, amount_str = callback.data.split("_")
        amount = float(amount_str)
        uid = callback.from_user.id

        cur.execute("""
            INSERT INTO portfolio (user_id, coin, amount)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id, coin) DO UPDATE SET amount = amount + ?
        """, (uid, coin, amount, amount))
        conn.commit()

        await callback.answer(f"✅ Added {amount} {coin}")
        await portfolio(callback)  # Refresh portfolio view
    except:
        await callback.answer("Error adding")

async def main():
    print("🚀 SoSoAgent Bot — Fully Button-Driven!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
