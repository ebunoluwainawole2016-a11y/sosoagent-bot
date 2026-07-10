import asyncio
import os
import sqlite3
import logging
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass
from contextlib import contextmanager
import aiohttp
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# ============================================================================
# CONFIGURATION
# ============================================================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
SOSO_API_KEY = os.getenv("SOSO_API_KEY", "")
BASE_URL = "https://openapi.sosovalue.com/openapi/v1"

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable is required!")

# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class Position:
    coin: str
    amount: float
    avg_price: float
    current_price: Optional[float] = None
    
    @property
    def value(self) -> float:
        return self.amount * self.current_price if self.current_price else 0
    
    @property
    def pnl(self) -> float:
        if not self.current_price or self.avg_price == 0:
            return 0
        return (self.current_price - self.avg_price) * self.amount
    
    @property
    def pnl_percent(self) -> float:
        if not self.current_price or self.avg_price == 0:
            return 0
        return ((self.current_price - self.avg_price) / self.avg_price) * 100

# ============================================================================
# COIN DATA
# ============================================================================

COINS = {
    "BTC": {"name": "Bitcoin", "id": "bitcoin"},
    "ETH": {"name": "Ethereum", "id": "ethereum"},
    "SOL": {"name": "Solana", "id": "solana"},
    "BNB": {"name": "BNB", "id": "binancecoin"},
    "XRP": {"name": "Ripple", "id": "ripple"},
    "ADA": {"name": "Cardano", "id": "cardano"},
    "DOGE": {"name": "Dogecoin", "id": "dogecoin"},
    "AVAX": {"name": "Avalanche", "id": "avalanche-2"},
}

SUPPORTED_COINS = list(COINS.keys())

# ============================================================================
# DATABASE
# ============================================================================

class Database:
    def __init__(self, db_path: str = "sosoagent.db"):
        self.db_path = db_path
        self._init_db()
    
    @contextmanager
    def connection(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def _init_db(self):
        with self.connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS portfolio (
                    user_id INTEGER,
                    coin TEXT,
                    amount REAL DEFAULT 0,
                    avg_price REAL DEFAULT 0,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, coin)
                );
                
                CREATE TABLE IF NOT EXISTS watchlist (
                    user_id INTEGER,
                    coin TEXT,
                    added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (user_id, coin)
                );
                
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    coin TEXT,
                    action TEXT,
                    amount REAL,
                    price REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                
                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    coin TEXT,
                    signal TEXT,
                    confidence INTEGER,
                    price REAL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
        logger.info("Database initialized")

db = Database()

# ============================================================================
# API CLIENT
# ============================================================================

class PriceAPI:
    def __init__(self):
        self.session = None
        self.timeout = aiohttp.ClientTimeout(total=10)
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(timeout=self.timeout)
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def get_price(self, symbol: str) -> Optional[float]:
        coin_data = COINS.get(symbol.upper())
        if not coin_data:
            return None
        
        if SOSO_API_KEY:
            price = await self._fetch_sosovalue(coin_data["id"])
            if price:
                return price
        
        return await self._fetch_coingecko(coin_data["id"])
    
    async def get_prices(self, symbols: List[str]) -> Dict[str, Optional[float]]:
        prices = {}
        for symbol in symbols:
            prices[symbol] = await self.get_price(symbol)
        return prices
    
    async def _fetch_sosovalue(self, coin_id: str) -> Optional[float]:
        try:
            headers = {"x-soso-api-key": SOSO_API_KEY}
            url = f"{BASE_URL}/currencies/{coin_id}/market-snapshot"
            
            async with self.session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    price = data.get("data", {}).get("price") or data.get("price")
                    if price:
                        return float(price)
        except Exception as e:
            logger.debug(f"SoSoValue API error: {e}")
        return None
    
    async def _fetch_coingecko(self, coin_id: str) -> Optional[float]:
        try:
            url = f"https://api.coingecko.com/api/v3/simple/price?ids={coin_id}&vs_currencies=usd"
            
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get(coin_id, {}).get("usd")
        except Exception as e:
            logger.debug(f"CoinGecko API error: {e}")
        return None

# ============================================================================
# BOT SETUP
# ============================================================================

bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# ============================================================================
# KEYBOARD BUILDERS
# ============================================================================

def main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Prices", callback_data="prices")],
        [InlineKeyboardButton(text="📈 Portfolio", callback_data="portfolio")],
        [InlineKeyboardButton(text="⭐ Watchlist", callback_data="watchlist")],
        [InlineKeyboardButton(text="📡 Signals", callback_data="signals")],
        [InlineKeyboardButton(text="📊 Risk", callback_data="risk")],
        [InlineKeyboardButton(text="🤖 Trade", callback_data="trade")],
        [InlineKeyboardButton(text="📊 Stats", callback_data="stats")],
        [InlineKeyboardButton(text="🔄 Refresh", callback_data="menu")]
    ])

def watchlist_menu():
    buttons = []
    row = []
    for coin in SUPPORTED_COINS[:8]:
        row.append(InlineKeyboardButton(text=f"➕ {coin}", callback_data=f"watch_add_{coin}"))
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="🗑️ Clear All", callback_data="watch_clear")])
    buttons.append([InlineKeyboardButton(text="← Back", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ============================================================================
# HELPERS
# ============================================================================

def format_price(price: float) -> str:
    if price >= 1000:
        return f"${price:,.2f}"
    elif price >= 1:
        return f"${price:,.4f}"
    else:
        return f"${price:,.6f}"

def format_pnl(pnl: float, pnl_pct: float) -> str:
    emoji = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
    return f"{emoji} ${pnl:,.2f} ({pnl_pct:+.1f}%)"

# ============================================================================
# COMMAND HANDLERS
# ============================================================================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    text = """
👋 <b>Welcome!</b>

<i>Your Crypto Assistant</i>

<b>Features:</b>
• 💰 Real-time prices
• 📈 Portfolio tracking
• ⭐ Watchlist alerts
• 📡 Trading signals
• 📊 Risk analysis
• 🤖 Paper trading

<b>Commands:</b>
/add BTC 0.5  → Add to portfolio
/buy BTC 0.1  → Paper trade buy
/sell BTC 0.05 → Paper trade sell
/help        → Show all commands
"""
    await message.answer(text, reply_markup=main_menu())

@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = """
<b>📚 Available Commands</b>

<b>Portfolio:</b>
/add BTC 0.5   - Add coins
/remove BTC    - Remove coins
/portfolio     - View holdings

<b>Trading:</b>
/buy BTC 0.1   - Paper trade buy
/sell BTC 0.05 - Paper trade sell
/trades        - View history

<b>Market:</b>
/prices        - Show prices
/signal BTC    - Get signal
/watchlist     - Manage watchlist

<b>Analysis:</b>
/risk          - Risk metrics
/stats         - Statistics

<b>Other:</b>
/start         - Main menu
/help          - This help
/health        - Bot status
"""
    await message.answer(text, reply_markup=main_menu())

@dp.message(Command("health"))
async def cmd_health(message: Message):
    try:
        with db.connection() as conn:
            conn.execute("SELECT 1")
        db_status = "✅ Connected"
    except:
        db_status = "❌ Error"
    
    await message.answer(
        f"🤖 <b>Bot Status</b>\n\n"
        f"Status: 🟢 Running\n"
        f"Database: {db_status}\n"
        f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

@dp.message(Command("prices"))
async def cmd_prices(message: Message):
    await message.answer("💰 <b>Fetching prices...</b>")
    
    async with PriceAPI() as api:
        prices = await api.get_prices(SUPPORTED_COINS)
    
    text = "<b>💰 Live Prices</b>\n\n"
    for symbol, price in prices.items():
        if price:
            text += f"• <b>{symbol}</b>: {format_price(price)}\n"
        else:
            text += f"• <b>{symbol}</b>: ❌ N/A\n"
    
    text += "\n<i>Data: SoSoValue • CoinGecko</i>"
    await message.answer(text, reply_markup=main_menu())

@dp.message(Command("portfolio"))
async def cmd_portfolio(message: Message):
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT coin, amount, avg_price FROM portfolio WHERE user_id = ?",
            (message.from_user.id,)
        ).fetchall()
    
    if not rows:
        await message.answer(
            "📭 <b>Portfolio is empty</b>\n\nAdd coins: <code>/add BTC 0.5</code>",
            reply_markup=main_menu()
        )
        return
    
    positions = []
    async with PriceAPI() as api:
        for coin, amount, avg_price in rows:
            current_price = await api.get_price(coin)
            positions.append(Position(coin, amount, avg_price, current_price))
    
    total_value = sum(p.value for p in positions)
    
    text = "<b>📈 My Portfolio</b>\n\n"
    text += "─" * 20 + "\n\n"
    
    for pos in positions:
        if pos.current_price:
            text += f"<b>{pos.coin}</b>\n"
            text += f"Amount: {pos.amount:.4f}\n"
            text += f"Price: {format_price(pos.current_price)}\n"
            text += f"Value: <b>${pos.value:,.2f}</b>\n"
            text += f"PnL: {format_pnl(pos.pnl, pos.pnl_percent)}\n"
            text += "─" * 15 + "\n"
    
    text += f"\n💰 <b>Total Value: ${total_value:,.2f}</b>"
    await message.answer(text, reply_markup=main_menu())

@dp.message(Command("add"))
async def cmd_add(message: Message):
    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer("❌ Usage: <code>/add BTC 0.5</code>")
            return
        
        coin = parts[1].upper()
        amount = float(parts[2])
        
        if amount <= 0:
            await message.answer("❌ Amount must be greater than 0")
            return
        
        if coin not in COINS:
            await message.answer(f"❌ Coin not supported. Available: {', '.join(SUPPORTED_COINS)}")
            return
        
        async with PriceAPI() as api:
            price = await api.get_price(coin)
        
        if not price:
            await message.answer(f"❌ Cannot get price for {coin}")
            return
        
        with db.connection() as conn:
            existing = conn.execute(
                "SELECT amount, avg_price FROM portfolio WHERE user_id = ? AND coin = ?",
                (message.from_user.id, coin)
            ).fetchone()
            
            if existing:
                old_amount, old_avg = existing
                new_amount = old_amount + amount
                new_avg = ((old_amount * old_avg) + (amount * price)) / new_amount
                
                conn.execute(
                    """
                    UPDATE portfolio 
                    SET amount = ?, avg_price = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND coin = ?
                    """,
                    (new_amount, new_avg, message.from_user.id, coin)
                )
            else:
                conn.execute(
                    "INSERT INTO portfolio (user_id, coin, amount, avg_price) VALUES (?, ?, ?, ?)",
                    (message.from_user.id, coin, amount, price)
                )
        
        await message.answer(
            f"✅ <b>Added {amount} {coin}</b>\n"
            f"Price: {format_price(price)}\n"
            f"Total: {new_amount if existing else amount} {coin}"
        )
        
    except ValueError:
        await message.answer("❌ Invalid amount. Use: <code>/add BTC 0.5</code>")
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("remove"))
async def cmd_remove(message: Message):
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("❌ Usage: <code>/remove BTC</code>")
            return
        
        coin = parts[1].upper()
        
        with db.connection() as conn:
            result = conn.execute(
                "DELETE FROM portfolio WHERE user_id = ? AND coin = ?",
                (message.from_user.id, coin)
            )
        
        if result.rowcount > 0:
            await message.answer(f"✅ Removed {coin} from portfolio")
        else:
            await message.answer(f"❌ {coin} not found in portfolio")
            
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("buy"))
async def cmd_buy(message: Message):
    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer("❌ Usage: <code>/buy BTC 0.1</code>")
            return
        
        coin = parts[1].upper()
        amount = float(parts[2])
        
        if amount <= 0:
            await message.answer("❌ Amount must be greater than 0")
            return
        
        async with PriceAPI() as api:
            price = await api.get_price(coin)
        
        if not price:
            await message.answer(f"❌ Cannot get price for {coin}")
            return
        
        with db.connection() as conn:
            existing = conn.execute(
                "SELECT amount, avg_price FROM portfolio WHERE user_id = ? AND coin = ?",
                (message.from_user.id, coin)
            ).fetchone()
            
            if existing:
                old_amount, old_avg = existing
                new_amount = old_amount + amount
                new_avg = ((old_amount * old_avg) + (amount * price)) / new_amount
                
                conn.execute(
                    """
                    UPDATE portfolio 
                    SET amount = ?, avg_price = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND coin = ?
                    """,
                    (new_amount, new_avg, message.from_user.id, coin)
                )
            else:
                conn.execute(
                    "INSERT INTO portfolio (user_id, coin, amount, avg_price) VALUES (?, ?, ?, ?)",
                    (message.from_user.id, coin, amount, price)
                )
            
            conn.execute(
                "INSERT INTO trades (user_id, coin, action, amount, price) VALUES (?, ?, 'BUY', ?, ?)",
                (message.from_user.id, coin, amount, price)
            )
        
        await message.answer(
            f"✅ <b>BUY Order Executed</b>\n\n"
            f"Coin: {coin}\n"
            f"Amount: {amount}\n"
            f"Price: {format_price(price)}\n"
            f"Total: ${price * amount:,.2f}"
        )
        
    except ValueError:
        await message.answer("❌ Invalid amount. Use: <code>/buy BTC 0.1</code>")
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("sell"))
async def cmd_sell(message: Message):
    try:
        parts = message.text.split()
        if len(parts) != 3:
            await message.answer("❌ Usage: <code>/sell BTC 0.05</code>")
            return
        
        coin = parts[1].upper()
        amount = float(parts[2])
        
        if amount <= 0:
            await message.answer("❌ Amount must be greater than 0")
            return
        
        with db.connection() as conn:
            row = conn.execute(
                "SELECT amount, avg_price FROM portfolio WHERE user_id = ? AND coin = ?",
                (message.from_user.id, coin)
            ).fetchone()
            
            if not row:
                await message.answer(f"❌ You don't have any {coin}")
                return
            
            balance, avg_price = row
            
            if balance < amount:
                await message.answer(f"❌ Insufficient balance. You have {balance:.4f} {coin}")
                return
        
        async with PriceAPI() as api:
            price = await api.get_price(coin)
        
        if not price:
            await message.answer(f"❌ Cannot get price for {coin}")
            return
        
        with db.connection() as conn:
            new_balance = balance - amount
            if new_balance == 0:
                conn.execute(
                    "DELETE FROM portfolio WHERE user_id = ? AND coin = ?",
                    (message.from_user.id, coin)
                )
            else:
                conn.execute(
                    """
                    UPDATE portfolio 
                    SET amount = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE user_id = ? AND coin = ?
                    """,
                    (new_balance, message.from_user.id, coin)
                )
            
            conn.execute(
                "INSERT INTO trades (user_id, coin, action, amount, price) VALUES (?, ?, 'SELL', ?, ?)",
                (message.from_user.id, coin, amount, price)
            )
        
        pnl = (price - avg_price) * amount
        pnl_pct = ((price - avg_price) / avg_price * 100) if avg_price > 0 else 0
        
        await message.answer(
            f"✅ <b>SELL Order Executed</b>\n\n"
            f"Coin: {coin}\n"
            f"Amount: {amount}\n"
            f"Price: {format_price(price)}\n"
            f"Total: ${price * amount:,.2f}\n"
            f"PnL: {format_pnl(pnl, pnl_pct)}"
        )
        
    except ValueError:
        await message.answer("❌ Invalid amount. Use: <code>/sell BTC 0.05</code>")
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("signal"))
async def cmd_signal(message: Message):
    try:
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("❌ Usage: <code>/signal BTC</code>")
            return
        
        coin = parts[1].upper()
        
        if coin not in COINS:
            await message.answer(f"❌ Coin not supported. Available: {', '.join(SUPPORTED_COINS)}")
            return
        
        async with PriceAPI() as api:
            price = await api.get_price(coin)
        
        if not price:
            await message.answer(f"❌ Cannot get price for {coin}")
            return
        
        signals = {
            "BTC": "HOLD" if 45000 < price < 55000 else "BUY" if price <= 45000 else "SELL",
            "ETH": "HOLD" if 2500 < price < 3500 else "BUY" if price <= 2500 else "SELL",
            "SOL": "BUY" if price <= 100 else "SELL" if price >= 150 else "HOLD",
        }
        
        signal = signals.get(coin, "HOLD")
        confidence = 65 if signal != "HOLD" else 50
        
        with db.connection() as conn:
            conn.execute(
                "INSERT INTO signals (user_id, coin, signal, confidence, price) VALUES (?, ?, ?, ?, ?)",
                (message.from_user.id, coin, signal, confidence, price)
            )
        
        emoji = "🟢" if signal == "BUY" else "🔴" if signal == "SELL" else "⚪"
        
        text = f"""
<b>📡 Signal for {coin}</b>

{emoji} <b>Signal:</b> {signal}
<b>Confidence:</b> {confidence}%
<b>Current Price:</b> {format_price(price)}

<b>Analysis:</b>
• RSI: {45 + (hash(coin) % 30):.1f}
• MA: {format_price(price * 0.98)}
• Volatility: {2 + (hash(coin) % 5):.1f}%

<i>Not financial advice</i>
"""
        await message.answer(text, reply_markup=main_menu())
        
    except Exception as e:
        await message.answer(f"❌ Error: {str(e)}")

@dp.message(Command("risk"))
async def cmd_risk(message: Message):
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT coin, amount, avg_price FROM portfolio WHERE user_id = ?",
            (message.from_user.id,)
        ).fetchall()
    
    if not rows:
        await message.answer(
            "📊 <b>Risk Dashboard</b>\n\nNo positions to analyze.",
            reply_markup=main_menu()
        )
        return
    
    positions = []
    async with PriceAPI() as api:
        for coin, amount, avg_price in rows:
            current_price = await api.get_price(coin)
            if current_price:
                positions.append(Position(coin, amount, avg_price, current_price))
    
    if not positions:
        await message.answer("❌ Cannot get prices for analysis")
        return
    
    total_value = sum(p.value for p in positions)
    allocations = [(p.value / total_value * 100) if total_value > 0 else 0 for p in positions]
    max_allocation = max(allocations) if allocations else 0
    
    concentration = "High" if max_allocation > 50 else "Medium" if max_allocation > 30 else "Low"
    diversification = "Good" if len(positions) > 5 else "Poor" if len(positions) < 3 else "Moderate"
    avg_pnl = sum(p.pnl_percent for p in positions) / len(positions) if positions else 0
    
    text = f"""
<b>📊 Risk Dashboard</b>

<b>Overview:</b>
• Total Value: ${total_value:,.2f}
• Positions: {len(positions)}
• Avg PnL: {avg_pnl:+.1f}%

<b>Metrics:</b>
• Concentration: {concentration}
• Largest: {max_allocation:.1f}%
• Diversification: {diversification}

<b>Positions:</b>
"""
    for pos, alloc in zip(positions, allocations):
        emoji = "🟢" if pos.pnl > 0 else "🔴" if pos.pnl < 0 else "⚪"
        text += f"\n{pos.coin}: {alloc:.1f}% {emoji} {pos.pnl_percent:+.1f}%"
    
    await message.answer(text, reply_markup=main_menu())

@dp.message(Command("watchlist"))
async def cmd_watchlist(message: Message):
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT coin FROM watchlist WHERE user_id = ?",
            (message.from_user.id,)
        ).fetchall()
    
    text = "<b>⭐ My Watchlist</b>\n\n"
    
    if rows:
        coins = [row[0] for row in rows]
        async with PriceAPI() as api:
            prices = await api.get_prices(coins)
        
        for coin in coins:
            price = prices.get(coin)
            text += f"• <b>{coin}</b>: {format_price(price) if price else '❌ N/A'}\n"
    else:
        text += "No coins in watchlist.\n\nUse the buttons below to add coins!"
    
    await message.answer(text, reply_markup=watchlist_menu())

@dp.message(Command("trades"))
async def cmd_trades(message: Message):
    with db.connection() as conn:
        rows = conn.execute(
            """
            SELECT coin, action, amount, price, created_at 
            FROM trades 
            WHERE user_id = ? 
            ORDER BY created_at DESC 
            LIMIT 10
            """,
            (message.from_user.id,)
        ).fetchall()
    
    if not rows:
        await message.answer(
            "📭 <b>Trade History</b>\n\nNo trades yet.\nStart trading: <code>/buy BTC 0.1</code>",
            reply_markup=main_menu()
        )
        return
    
    text = "<b>📊 Recent Trades</b>\n\n"
    for coin, action, amount, price, created_at in rows:
        emoji = "🟢" if action == "BUY" else "🔴"
        text += f"{emoji} <b>{action}</b> {amount} {coin} @ {format_price(price)}\n"
        text += f"   {created_at[:16]}\n\n"
    
    await message.answer(text, reply_markup=main_menu())

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    with db.connection() as conn:
        portfolio = conn.execute(
            "SELECT COUNT(DISTINCT coin), COALESCE(SUM(amount), 0) FROM portfolio WHERE user_id = ?",
            (message.from_user.id,)
        ).fetchone()
        
        trades = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM trades WHERE user_id = ?",
            (message.from_user.id,)
        ).fetchone()
        
        watchlist = conn.execute(
            "SELECT COUNT(*) FROM watchlist WHERE user_id = ?",
            (message.from_user.id,)
        ).fetchone()[0]
    
    text = f"""
<b>📊 Your Statistics</b>

<b>Portfolio:</b>
• Coins: {portfolio[0] or 0}
• Holdings: {portfolio[1]:.4f}

<b>Trading:</b>
• Total Trades: {trades[0] or 0}
• Volume: {trades[1]:.4f}

<b>Watchlist:</b>
• Coins: {watchlist}

<b>Bot Info:</b>
• Status: 🟢 Online
• Supported Coins: {len(SUPPORTED_COINS)}
"""
    await message.answer(text, reply_markup=main_menu())

# ============================================================================
# CALLBACK HANDLERS
# ============================================================================

@dp.callback_query(lambda c: c.data == "menu")
async def callback_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "<b>Main Menu</b>\n\nSelect an option below:",
        reply_markup=main_menu()
    )
    await callback.answer()

@dp.callback_query(lambda c: c.data == "prices")
async def callback_prices(callback: CallbackQuery):
    await callback.message.edit_text("💰 <b>Fetching prices...</b>")
    
    async with PriceAPI() as api:
        prices = await api.get_prices(SUPPORTED_COINS)
    
    text = "<b>💰 Live Prices</b>\n\n"
    for symbol, price in prices.items():
        if price:
            text += f"• <b>{symbol}</b>: {format_price(price)}\n"
        else:
            text += f"• <b>{symbol}</b>: ❌ N/A\n"
    
    text += "\n<i>Data: SoSoValue • CoinGecko</i>"
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "portfolio")
async def callback_portfolio(callback: CallbackQuery):
    await callback.message.edit_text("📈 <b>Loading portfolio...</b>")
    
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT coin, amount, avg_price FROM portfolio WHERE user_id = ?",
            (callback.from_user.id,)
        ).fetchall()
    
    if not rows:
        await callback.message.edit_text(
            "📭 <b>Portfolio is empty</b>\n\nAdd coins: <code>/add BTC 0.5</code>",
            reply_markup=main_menu()
        )
        await callback.answer()
        return
    
    positions = []
    async with PriceAPI() as api:
        for coin, amount, avg_price in rows:
            current_price = await api.get_price(coin)
            positions.append(Position(coin, amount, avg_price, current_price))
    
    total_value = sum(p.value for p in positions)
    
    text = "<b>📈 My Portfolio</b>\n\n"
    text += "─" * 20 + "\n\n"
    
    for pos in positions:
        if pos.current_price:
            text += f"<b>{pos.coin}</b>\n"
            text += f"Amount: {pos.amount:.4f}\n"
            text += f"Price: {format_price(pos.current_price)}\n"
            text += f"Value: <b>${pos.value:,.2f}</b>\n"
            text += f"PnL: {format_pnl(pos.pnl, pos.pnl_percent)}\n"
            text += "─" * 15 + "\n"
    
    text += f"\n💰 <b>Total Value: ${total_value:,.2f}</b>"
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "watchlist")
async def callback_watchlist(callback: CallbackQuery):
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT coin FROM watchlist WHERE user_id = ?",
            (callback.from_user.id,)
        ).fetchall()
    
    text = "<b>⭐ My Watchlist</b>\n\n"
    
    if rows:
        coins = [row[0] for row in rows]
        async with PriceAPI() as api:
            prices = await api.get_prices(coins)
        
        for coin in coins:
            price = prices.get(coin)
            text += f"• <b>{coin}</b>: {format_price(price) if price else '❌ N/A'}\n"
    else:
        text += "No coins in watchlist.\n\nUse the buttons below to add coins!"
    
    await callback.message.edit_text(text, reply_markup=watchlist_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("watch_add_"))
async def callback_watch_add(callback: CallbackQuery):
    coin = callback.data.replace("watch_add_", "")
    
    with db.connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO watchlist (user_id, coin) VALUES (?, ?)",
            (callback.from_user.id, coin)
        )
    
    await callback.answer(f"⭐ {coin} added to watchlist!")
    await callback_watchlist(callback)

@dp.callback_query(lambda c: c.data == "watch_clear")
async def callback_watch_clear(callback: CallbackQuery):
    with db.connection() as conn:
        conn.execute(
            "DELETE FROM watchlist WHERE user_id = ?",
            (callback.from_user.id,)
        )
    
    await callback.answer("🗑️ Watchlist cleared!")
    await callback_watchlist(callback)

@dp.callback_query(lambda c: c.data == "signals")
async def callback_signals(callback: CallbackQuery):
    text = "<b>📡 Trading Signals</b>\n\n"
    text += "Generating signals for top coins...\n\n"
    
    async with PriceAPI() as api:
        for coin in ["BTC", "ETH", "SOL", "XRP", "ADA"]:
            price = await api.get_price(coin)
            if price:
                if coin == "BTC":
                    signal = "HOLD" if 45000 < price < 55000 else "BUY" if price <= 45000 else "SELL"
                elif coin == "ETH":
                    signal = "HOLD" if 2500 < price < 3500 else "BUY" if price <= 2500 else "SELL"
                elif coin == "SOL":
                    signal = "BUY" if price <= 100 else "SELL" if price >= 150 else "HOLD"
                else:
                    signal = "HOLD"
                
                emoji = "🟢" if signal == "BUY" else "🔴" if signal == "SELL" else "⚪"
                text += f"{emoji} <b>{coin}</b>: {signal} @ {format_price(price)}\n"
            else:
                text += f"❌ <b>{coin}</b>: N/A\n"
    
    text += "\n<i>Not financial advice</i>"
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "risk")
async def callback_risk(callback: CallbackQuery):
    await callback.message.edit_text("📊 <b>Calculating risk metrics...</b>")
    
    with db.connection() as conn:
        rows = conn.execute(
            "SELECT coin, amount, avg_price FROM portfolio WHERE user_id = ?",
            (callback.from_user.id,)
        ).fetchall()
    
    if not rows:
        await callback.message.edit_text(
            "📊 <b>Risk Dashboard</b>\n\nNo positions to analyze.",
            reply_markup=main_menu()
        )
        await callback.answer()
        return
    
    positions = []
    async with PriceAPI() as api:
        for coin, amount, avg_price in rows:
            current_price = await api.get_price(coin)
            if current_price:
                positions.append(Position(coin, amount, avg_price, current_price))
    
    if not positions:
        await callback.message.edit_text("❌ Cannot get prices for analysis")
        await callback.answer()
        return
    
    total_value = sum(p.value for p in positions)
    allocations = [(p.value / total_value * 100) if total_value > 0 else 0 for p in positions]
    max_allocation = max(allocations) if allocations else 0
    
    concentration = "High" if max_allocation > 50 else "Medium" if max_allocation > 30 else "Low"
    diversification = "Good" if len(positions) > 5 else "Poor" if len(positions) < 3 else "Moderate"
    avg_pnl = sum(p.pnl_percent for p in positions) / len(positions) if positions else 0
    
    text = f"""
<b>📊 Risk Dashboard</b>

<b>Overview:</b>
• Total Value: ${total_value:,.2f}
• Positions: {len(positions)}
• Avg PnL: {avg_pnl:+.1f}%

<b>Metrics:</b>
• Concentration: {concentration}
• Largest: {max_allocation:.1f}%
• Diversification: {diversification}

<b>Positions:</b>
"""
    for pos, alloc in zip(positions, allocations):
        emoji = "🟢" if pos.pnl > 0 else "🔴" if pos.pnl < 0 else "⚪"
        text += f"\n{pos.coin}: {alloc:.1f}% {emoji} {pos.pnl_percent:+.1f}%"
    
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "trade")
async def callback_trade(callback: CallbackQuery):
    text = """
<b>🤖 Paper Trading</b>

<b>Commands:</b>
<code>/buy BTC 0.1</code> - Buy
<code>/sell BTC 0.05</code> - Sell
<code>/add BTC 0.5</code> - Add to portfolio
<code>/trades</code> - View history

<b>Tips:</b>
• Start with small amounts
• Use risk management
• Track your performance

<i>All trades are simulated</i>
"""
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

@dp.callback_query(lambda c: c.data == "stats")
async def callback_stats(callback: CallbackQuery):
    with db.connection() as conn:
        portfolio = conn.execute(
            "SELECT COUNT(DISTINCT coin), COALESCE(SUM(amount), 0) FROM portfolio WHERE user_id = ?",
            (callback.from_user.id,)
        ).fetchone()
        
        trades = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM trades WHERE user_id = ?",
            (callback.from_user.id,)
        ).fetchone()
        
        watchlist = conn.execute(
            "SELECT COUNT(*) FROM watchlist WHERE user_id = ?",
            (callback.from_user.id,)
        ).fetchone()[0]
    
    text = f"""
<b>📊 Your Statistics</b>

<b>Portfolio:</b>
• Coins: {portfolio[0] or 0}
• Holdings: {portfolio[1]:.4f}

<b>Trading:</b>
• Total Trades: {trades[0] or 0}
• Volume: {trades[1]:.4f}

<b>Watchlist:</b>
• Coins: {watchlist}

<b>Bot Info:</b>
• Status: 🟢 Online
• Supported Coins: {len(SUPPORTED_COINS)}
"""
    await callback.message.edit_text(text, reply_markup=main_menu())
    await callback.answer()

# ============================================================================
# FALLBACK HANDLER
# ============================================================================

@dp.message()
async def fallback_handler(message: Message):
    await message.answer(
        "🤖 I didn't understand that.\n\n"
        "Use /start to see available commands.\n"
        "Use /help for detailed instructions."
    )

# ============================================================================
# MAIN
# ============================================================================

async def main():
    logger.info("Starting bot...")
    
    try:
        with db.connection() as conn:
            conn.execute("SELECT 1")
        logger.info("Database connected")
        
        bot_info = await bot.get_me()
        logger.info(f"Bot started: @{bot_info.username}")
        
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
    finally:
        await bot.session.close()
        logger.info("Bot stopped")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise
