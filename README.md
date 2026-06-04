SoSoAgent Bot 🚀

Your Personal On-Chain Finance Co-Pilot

SoSoAgent Bot is a smart Telegram bot that helps users monitor cryptocurrency markets, track portfolio performance, and access market intelligence through a simple, mobile-first Telegram experience.

Built for the SoSoValue Buildathon, the bot combines institutional-grade market insights with reliable public data sources to deliver real-time information directly inside Telegram.


🎯 Project Vision

Crypto users often face:

- Information overload across multiple platforms
- Manual portfolio tracking
- Delayed access to market-moving information
- Complex dashboards that are difficult to navigate

SoSoAgent Bot addresses these challenges by providing a streamlined Telegram interface that delivers essential market insights in one place.


💡 Why SoSoAgent Bot?

Many crypto tools are designed for advanced traders and present large amounts of raw data.

SoSoAgent Bot focuses on:

- Simplicity
- Accessibility
- Reliability
- Mobile-first user experience

Users can quickly access prices, portfolio information, market sentiment, ETF data, and news without leaving Telegram.


🏗️ Architecture

Intelligence Layer

- SoSoValue API (Primary Source)
- CoinGecko API (Price Fallback)
- CryptoCompare API (News Feed)
- Alternative.me API (Fear & Greed Index)

Data Layer

- SQLite Database
- Persistent Portfolio Storage
- Real-Time Market Data

Delivery Layer

- Telegram Bot Interface
- Inline Keyboard Navigation
- Async Event Processing (Aiogram)


🛠️ Tech Stack

- Python 3.11+
- Aiogram 3.x
- SQLite
- AioHTTP
- Python-Dotenv
- SoSoValue API
- CoinGecko API
- CryptoCompare API


🚀 Features

Market Data

- Live BTC, ETH and SOL prices
- Real-time market updates
- Market summary dashboard

Portfolio Tracking

- Add assets to portfolio
- Persistent portfolio storage
- Live portfolio valuation
- Total portfolio value calculation

Market Intelligence

- Fear & Greed Index
- ETF Market Overview
- Latest Crypto News

User Experience

- Fully button-driven interface
- Fast Telegram navigation
- Mobile-friendly design


📦 Installation

Clone Repository

git clone https://github.com/yourusername/sosoagent-bot.git
cd sosoagent-bot

Install Dependencies

pip install -r requirements.txt

Configure Environment Variables

Create a ".env" file:

BOT_TOKEN=your_telegram_bot_token
SOSO_API_KEY=your_sosovalue_api_key

Run Bot

python bot.py


🌊 Development Roadmap

Wave 1 – MVP ✅

- Telegram Bot Setup
- Live Price Tracking
- Initial Portfolio Tracking
- Multi-API Integration

Wave 2 – Enhanced Intelligence ✅

- Persistent Portfolio Storage
- ETF Integration
- Crypto News Feed
- Fear & Greed Index
- Improved User Experience
- Production Deployment

Wave 3 – Planned Features

- Price Alerts
- Watchlists
- AI Market Commentary
- Solana Wallet Tracking
- Portfolio Analytics

Wave 4 – Advanced Intelligence

- Personalized Insights
- AI Market Summaries
- Risk Analysis
- Smart Portfolio Recommendations


🏆 Competitive Advantages

- Simple Telegram-native experience
- Multi-source data reliability
- Persistent portfolio tracking
- Fast response times
- Mobile-first design
- Built specifically for crypto users


⚙️ Testing Notes

- API responses may take a few seconds depending on network conditions.
- Portfolio data is stored locally using SQLite.
- All major features are accessible through Telegram buttons.


⚠️ Disclaimer

This project is provided for educational and demonstration purposes only.

It does not provide financial advice. Always conduct your own research before making investment decisions.


🔗 Links

Live Bot:
https://t.me/sosoagent_bot


