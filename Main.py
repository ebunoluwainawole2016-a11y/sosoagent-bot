import asyncio
import os
import sqlite3
import aiohttp
from html import escape
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SOSO_API_KEY = os.getenv("SOSO_API_KEY")
BASE_URL = "https://openapi.sosovalue.com/openapi/v1"

if not BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN missing!")

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()

COIN_MAP = {
    "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
    "BNB": "binancecoin", "XRP": "ripple"
}

# Database
conn = sqlite3.connect("sosoagent.db", check_same_thread=False)
cur = conn.cursor()
cur.execute("""
CREATE TABLE IF NOT EXISTS portfolio(
    user_id INTEGER,
    coin TEXT,
    amount REAL,
    PRIMARY KEY(user_id, coin)
)
""")
cur.execute("""
CREATE TABLE IF NOT EXISTS watchlist(
    user_id INTEGER,
    coin TEXT,
    PRIMARY KEY(user_id, coin)
)
""")
conn.commit()

# Menus
def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Prices", callback_data="prices")],
        [InlineKeyboardButton(text="📊 Market Summary", callback_data="market")],
        [InlineKeyboardButton(text="😨 Fear & Greed", callback_data="fear")],
        [InlineKeyboardButton(text="📰 News", callback_data="news")],
        [InlineKeyboardButton(text="📈 ETF Flows", callback_data="etf")],
        [InlineKeyboardButton(text="📈 Portfolio", callback_data="portfolio")],
        [InlineKeyboardButton(text="⭐ Watchlist", callback_data="watchlist")],
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu")]
    ])

def watchlist_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ BTC", callback_data="add_watch_BTC"),
         InlineKeyboardButton(text="➕ ETH", callback_data="add_watch_ETH")],
        [InlineKeyboardButton(text="➕ SOL", callback_data="add_watch_SOL"),
         InlineKeyboardButton(text="➕ XRP", callback_data="add_watch_XRP")],
        [InlineKeyboardButton(text="➕ BNB", callback_data="add_watch_BNB"),
         InlineKeyboardButton(text="← Back", callback_data="menu")]
    ])

# API Helpers
async def soso_api_call(endpoint, params=None):
    if not SOSO_API_KEY:
        return None
    try:
        headers = {"x-soso-api-key": SOSO_API_KEY}
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=12)) as session:
            async with session.get(f"{BASE_URL}{endpoint}", headers=headers, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        print("SoSo Error:", e)
    return None

async def get_price(symbol):
    coin_id = COIN_MAP.get(symbol.upper())
    if not coin_id:
        return None

    data = await soso_api_call(f"/currencies/{coin_id}/market-snapshot")
    if data and isinstance(data, dict):
        try:
            price = data.get("data", {}).get("price") or data.get("price")
            if price:
                return float(price)
        except:
            pass

    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get(coin_id, {}).get("usd")
    except:
        pass

    # Binance fallback
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get(
                f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}USDT"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return float(data["price"])
    except:
        pass
    return None

async def get_fear_greed():
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get("https://api.alternative.me/fng/") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    item = data["data"][0]
                    return item["value"], item["value_classification"]
    except Exception as e:
        print("Fear & Greed Error:", e)
    return None, None

async def get_news():
    data = await soso_api_call("/news", {"limit": 5})
    if data:
        try:
            items = data.get("data", []) or data.get("items", [])
            if items:
                return [{"title": item.get("title", "News"), "url": item.get("url", "")} for item in items[:5]]
        except:
            pass

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get("https://min-api.cryptocompare.com/data/v2/news/?lang=EN") as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return [{"title": item.get("title"), "url": item.get("url")} for item in result.get("Data", [])[:5]]
    except Exception as e:
        print("News Error:", e)
    return [{"title": "Visit CoinDesk for latest crypto updates", "url": "https://www.coindesk.com/"}]

async def get_etf_data():
    data = await soso_api_call("/etfs/summary-history", {"limit": 7})
    if data:
        return {"source": "soso", "data": data}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
            async with session.get("https://api.coingecko.com/api/v3/global") as resp:
                if resp.status == 200:
                    cg = await resp.json()
                    return {
                        "source": "coingecko",
                        "market_cap": cg.get("data", {}).get("total_market_cap", {}).get("usd"),
                        "btc_dom": cg.get("data", {}).get("market_cap_percentage", {}).get("btc")
                    }
    except:
        pass
    return None

# Handlers
@dp.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "👋 <b>Welcome to SoSoAgent Bot!</b> 🚀\n\n"
        "Your On-Chain Finance Co-Pilot",
        reply_markup=main_menu()
    )

@dp.callback_query(lambda c: c.data == "menu")
async def show_menu(callback):
    await callback.message.edit_text("<b>Main Menu</b>", reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "prices")
async def prices(callback):
    text = "<b>💰 Live Prices</b>\n\n"
    for symbol in ["BTC", "ETH", "SOL", "XRP", "BNB"]:
        price = await get_price(symbol)
        if price:
            text += f"<b>{symbol}</b>: ${price:,.2f}\n"
        else:
            text += f"<b>{symbol}</b>: N/A\n"
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
    text = f"<b>😨 Fear & Greed</b>\n{value} — {label}" if value else "❌ Unavailable right now."
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "news")
async def news(callback):
    articles = await get_news()
    if not articles:
        text = "❌ No news available right now."
    else:
        text = "<b>📰 Latest Crypto News</b>\n\n"
        for article in articles:
            title = escape(article.get("title", "News"))[:80]
            url = article.get("url", "")
            text += f"• <b>{title}</b>\n{url}\n\n"
    await callback.message.edit_text(text, reply_markup=main_menu(), disable_web_page_preview=True)
    await callback.answer()

@dp.callback_query(lambda c: c.data == "etf")
async def etf(callback):
    data = await get_etf_data()
    text = "<b>📈 ETF & Market Overview</b>\n\n"
    if not data:
        text += "ETF data unavailable."
    elif data.get("source") == "coingecko":
        market_cap = data.get("market_cap")
        btc_dom = data.get("btc_dom")
        if market_cap:
            text += f"🌍 Global Market Cap: <b>${market_cap:,.0f}</b>\n"
        if btc_dom is not None:
            text += f"₿ BTC Dominance: <b>{btc_dom:.2f}%</b>\n"
        text += "\nUsing CoinGecko public data"
    elif data.get("source") == "soso":
        raw = data.get("data", {})
        text += "<b>Live ETF Data</b>\n\n"
        text += f"<code>{str(raw)[:3000]}</code>"
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "portfolio")
async def portfolio(callback):
    cur.execute("SELECT coin, amount FROM portfolio WHERE user_id=?", (callback.from_user.id,))
    rows = cur.fetchall()
    if not rows:
        text = "📭 <b>Portfolio is empty</b>"
    else:
        total = 0
        text = "<b>📈 My Portfolio</b>\n\n"
        for coin, amount in rows:
            price = await get_price(coin)
            if price:
                value = price * amount
                total += value
                text += f"🪙 <b>{coin}</b>\nAmount: {amount}\nValue: <b>${value:,.2f}</b>\n\n"
            else:
                text += f"🪙 <b>{coin}</b>\nAmount: {amount}\nValue: N/A\n\n"
        text += f"💰 <b>Total Value: ${total:,.2f}</b>"
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "watchlist")
async def watchlist(callback):
    cur.execute("SELECT coin FROM watchlist WHERE user_id=?", (callback.from_user.id,))
    rows = cur.fetchall()
    text = "<b>⭐ My Watchlist</b>\n\n"
    if rows:
        for (coin,) in rows:
            price = await get_price(coin)
            if price:
                text += f"• <b>{coin}</b>: ${price:,.2f}\n"
            else:
                text += f"• <b>{coin}</b>: N/A\n"
    else:
        text += "No coins added yet.\n\nTap buttons to add."
    await callback.message.edit_text(text, reply_markup=watchlist_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("add_watch_"))
async def add_watch_button(callback):
    coin = callback.data.replace("add_watch_", "")
    cur.execute("INSERT OR IGNORE INTO watchlist(user_id, coin) VALUES (?, ?)", 
                (callback.from_user.id, coin))
    conn.commit()
    await callback.answer(f"⭐ {coin} added")
    await watchlist(callback)

async def main():
    print("🚀 Starting SoSoAgent Bot...")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        print(f"❌ Error: {e}")
    finally:
        conn.close()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
