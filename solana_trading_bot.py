# “””

# SOLANA TRADING BOT — Telegram
Features: Price check, Buy/Sell alerts, Sniper, Portfolio
Stack: python-telegram-bot, Jupiter API, Dexscreener API

SETUP:

1. pip install python-telegram-bot solana solders requests aiohttp
1. Fill in your BOT_TOKEN and WALLET_PRIVATE_KEY below
1. python solana_trading_bot.py

COMMANDS:
/price <CA>        — Get token price from Dexscreener
/buy <CA> <SOL>    — Buy token with X SOL via Jupiter
/sell <CA> <%>     — Sell X% of token holding
/snipe <CA>        — Watch a CA and auto-buy on bonding
/portfolio         — Show all holdings + P&L
/alerts            — List active price alerts
/setalert <CA> <$> — Alert when token hits price
/stop              — Stop all snipers
“””

import os
import json
import asyncio
import logging
import aiohttp
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
ApplicationBuilder, CommandHandler, ContextTypes,
CallbackQueryHandler
)
from solders.keypair import Keypair  # type: ignore
from solders.pubkey import Pubkey    # type: ignore
import base58

# ──────────────────────────────────────────────

# CONFIG — Fill these in

# ──────────────────────────────────────────────

BOT_TOKEN = "8268631530:AAFAOsozKT5_TjxEiB-EYYN_Eo2Of2JkfsI"
”         # From @BotFather
WALLET_PRIVATE_KEY = “4rz8F4zcGEyBoadxJX33bP2SKYuEuB6L8SqeFQaQ7xTBimbBzFtrHPsyNCeQBxJC91t5S96j3CAnKQp7s4ounzyk”  # Base58 private key
AUTHORIZED_USER_ID = 7428453450                  # Your Telegram user ID (get via @userinfobot)

RPC_URL = “https://api.mainnet-beta.solana.com”
JUPITER_QUOTE_URL = “https://quote-api.jup.ag/v6/quote”
JUPITER_SWAP_URL  = “https://quote-api.jup.ag/v6/swap”
DEXSCREENER_URL   = “https://api.dexscreener.com/latest/dex/tokens”
SOL_MINT          = “So11111111111111111111111111111111111111112”
SLIPPAGE_BPS      = 300   # 3% slippage

logging.basicConfig(
format=”%(asctime)s - %(name)s - %(levelname)s - %(message)s”,
level=logging.INFO
)
logger = logging.getLogger(**name**)

# ──────────────────────────────────────────────

# IN-MEMORY STATE

# ──────────────────────────────────────────────

portfolio: dict = {}       # { CA: { “amount”: float, “avg_buy”: float, “symbol”: str } }
active_alerts: dict = {}   # { CA: { “target_price”: float, “symbol”: str } }
active_snipers: dict = {}  # { CA: asyncio.Task }

# ──────────────────────────────────────────────

# HELPERS

# ──────────────────────────────────────────────

def get_keypair() -> Keypair:
raw = base58.b58decode(WALLET_PRIVATE_KEY)
return Keypair.from_bytes(raw)

def auth(update: Update) -> bool:
return update.effective_user.id == AUTHORIZED_USER_ID

async def fetch_token_data(ca: str) -> dict | None:
“”“Fetch token data from Dexscreener.”””
url = f”{DEXSCREENER_URL}/{ca}”
async with aiohttp.ClientSession() as session:
async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
if resp.status != 200:
return None
data = await resp.json()
pairs = data.get(“pairs”)
if not pairs:
return None
# Return the highest liquidity Solana pair
sol_pairs = [p for p in pairs if p.get(“chainId”) == “solana”]
if not sol_pairs:
return None
return sorted(sol_pairs, key=lambda x: x.get(“liquidity”, {}).get(“usd”, 0), reverse=True)[0]

async def get_jupiter_quote(input_mint: str, output_mint: str, amount_lamports: int) -> dict | None:
“”“Get a Jupiter swap quote.”””
params = {
“inputMint”: input_mint,
“outputMint”: output_mint,
“amount”: str(amount_lamports),
“slippageBps”: str(SLIPPAGE_BPS),
}
async with aiohttp.ClientSession() as session:
async with session.get(JUPITER_QUOTE_URL, params=params,
timeout=aiohttp.ClientTimeout(total=10)) as resp:
if resp.status != 200:
return None
return await resp.json()

async def execute_jupiter_swap(quote: dict, keypair: Keypair) -> str | None:
“”“Execute swap via Jupiter and return transaction signature.”””
payload = {
“quoteResponse”: quote,
“userPublicKey”: str(keypair.pubkey()),
“wrapAndUnwrapSol”: True,
“dynamicComputeUnitLimit”: True,
“prioritizationFeeLamports”: “auto”,
}
async with aiohttp.ClientSession() as session:
async with session.post(JUPITER_SWAP_URL, json=payload,
timeout=aiohttp.ClientTimeout(total=20)) as resp:
if resp.status != 200:
return None
swap_data = await resp.json()

```
# Sign and send transaction
from solana.rpc.async_api import AsyncClient
from solders.transaction import VersionedTransaction  # type: ignore
import base64

swap_tx_bytes = base64.b64decode(swap_data["swapTransaction"])
tx = VersionedTransaction.from_bytes(swap_tx_bytes)
signed_tx = keypair.sign_message(bytes(tx.message))

async with AsyncClient(RPC_URL) as client:
    result = await client.send_raw_transaction(bytes(signed_tx))
    return str(result.value)
```

# ──────────────────────────────────────────────

# COMMAND: /start

# ──────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not auth(update):
await update.message.reply_text(“⛔ Unauthorized.”)
return

```
text = (
    "🤖 *Solana Trading Bot*\n\n"
    "Commands:\n"
    "`/price <CA>` — Token price\n"
    "`/buy <CA> <SOL>` — Buy token\n"
    "`/sell <CA> <%>` — Sell % of holding\n"
    "`/snipe <CA>` — Auto-snipe on bonding\n"
    "`/portfolio` — Holdings & P&L\n"
    "`/setalert <CA> <$>` — Price alert\n"
    "`/alerts` — Active alerts\n"
    "`/stop` — Stop all snipers\n"
)
await update.message.reply_text(text, parse_mode="Markdown")
```

# ──────────────────────────────────────────────

# COMMAND: /price

# ──────────────────────────────────────────────

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not auth(update): return
if not context.args:
await update.message.reply_text(“Usage: `/price <CA>`”, parse_mode=“Markdown”)
return

```
ca = context.args[0].strip()
msg = await update.message.reply_text("🔍 Fetching price...")

data = await fetch_token_data(ca)
if not data:
    await msg.edit_text("❌ Token not found on Dexscreener.")
    return

symbol   = data.get("baseToken", {}).get("symbol", "???")
name     = data.get("baseToken", {}).get("name", "")
price_usd = data.get("priceUsd", "N/A")
liq      = data.get("liquidity", {}).get("usd", 0)
vol_24h  = data.get("volume", {}).get("h24", 0)
change_1h = data.get("priceChange", {}).get("h1", 0)
change_24h = data.get("priceChange", {}).get("h24", 0)
dex_url  = data.get("url", "")

emoji_1h  = "🟢" if float(change_1h or 0) >= 0 else "🔴"
emoji_24h = "🟢" if float(change_24h or 0) >= 0 else "🔴"

text = (
    f"💰 *{symbol}* ({name})\n\n"
    f"Price: `${float(price_usd):.8f}`\n"
    f"Liquidity: `${liq:,.0f}`\n"
    f"Volume 24h: `${vol_24h:,.0f}`\n"
    f"{emoji_1h} 1h: `{change_1h}%`\n"
    f"{emoji_24h} 24h: `{change_24h}%`\n\n"
    f"[View on Dexscreener]({dex_url})"
)
keyboard = InlineKeyboardMarkup([
    [InlineKeyboardButton("🟢 Buy 0.1 SOL", callback_data=f"buy:{ca}:0.1"),
     InlineKeyboardButton("🟢 Buy 0.5 SOL", callback_data=f"buy:{ca}:0.5")]
])
await msg.edit_text(text, parse_mode="Markdown", reply_markup=keyboard,
                    disable_web_page_preview=True)
```

# ──────────────────────────────────────────────

# COMMAND: /buy

# ──────────────────────────────────────────────

async def buy(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not auth(update): return
if len(context.args) < 2:
await update.message.reply_text(“Usage: `/buy <CA> <SOL_amount>`”, parse_mode=“Markdown”)
return

```
ca  = context.args[0].strip()
try:
    sol_amount = float(context.args[1])
except ValueError:
    await update.message.reply_text("❌ Invalid SOL amount.")
    return

msg = await update.message.reply_text(f"⚡ Buying with {sol_amount} SOL...")

lamports = int(sol_amount * 1_000_000_000)
quote = await get_jupiter_quote(SOL_MINT, ca, lamports)
if not quote:
    await msg.edit_text("❌ Could not get Jupiter quote. Check CA or liquidity.")
    return

out_amount = int(quote.get("outAmount", 0))
keypair = get_keypair()

try:
    sig = await execute_jupiter_swap(quote, keypair)
except Exception as e:
    await msg.edit_text(f"❌ Swap failed: {e}")
    return

# Update portfolio
data = await fetch_token_data(ca)
symbol   = data.get("baseToken", {}).get("symbol", ca[:6]) if data else ca[:6]
price_usd = float(data.get("priceUsd", 0)) if data else 0

if ca in portfolio:
    old = portfolio[ca]
    total_amount = old["amount"] + out_amount
    total_cost   = old["avg_buy"] * old["amount"] + sol_amount
    portfolio[ca]["amount"]   = total_amount
    portfolio[ca]["avg_buy"]  = total_cost / total_amount
else:
    portfolio[ca] = {
        "symbol": symbol,
        "amount": out_amount,
        "avg_buy": price_usd,
        "sol_spent": sol_amount,
    }

await msg.edit_text(
    f"✅ *Buy Executed!*\n\n"
    f"Token: `{symbol}`\n"
    f"SOL Spent: `{sol_amount}`\n"
    f"Tokens Received: `{out_amount:,}`\n"
    f"Tx: `{sig}`\n"
    f"[View on Solscan](https://solscan.io/tx/{sig})",
    parse_mode="Markdown",
    disable_web_page_preview=True
)
```

# ──────────────────────────────────────────────

# COMMAND: /sell

# ──────────────────────────────────────────────

async def sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not auth(update): return
if len(context.args) < 2:
await update.message.reply_text(“Usage: `/sell <CA> <percent>`\nExample: `/sell <CA> 100`”, parse_mode=“Markdown”)
return

```
ca = context.args[0].strip()
try:
    pct = float(context.args[1])
except ValueError:
    await update.message.reply_text("❌ Invalid percentage.")
    return

if ca not in portfolio:
    await update.message.reply_text("❌ Token not in portfolio.")
    return

holding  = portfolio[ca]
sell_amt = int(holding["amount"] * pct / 100)
msg      = await update.message.reply_text(f"⚡ Selling {pct}% of {holding['symbol']}...")

quote = await get_jupiter_quote(ca, SOL_MINT, sell_amt)
if not quote:
    await msg.edit_text("❌ Could not get Jupiter quote.")
    return

keypair = get_keypair()
try:
    sig = await execute_jupiter_swap(quote, keypair)
except Exception as e:
    await msg.edit_text(f"❌ Swap failed: {e}")
    return

sol_received = int(quote.get("outAmount", 0)) / 1_000_000_000

if pct >= 100:
    del portfolio[ca]
else:
    portfolio[ca]["amount"] = int(holding["amount"] * (1 - pct / 100))

await msg.edit_text(
    f"✅ *Sell Executed!*\n\n"
    f"Token: `{holding['symbol']}`\n"
    f"Sold: `{pct}%`\n"
    f"SOL Received: `{sol_received:.4f} SOL`\n"
    f"Tx: `{sig}`\n"
    f"[View on Solscan](https://solscan.io/tx/{sig})",
    parse_mode="Markdown",
    disable_web_page_preview=True
)
```

# ──────────────────────────────────────────────

# COMMAND: /portfolio

# ──────────────────────────────────────────────

async def show_portfolio(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not auth(update): return
if not portfolio:
await update.message.reply_text(“📭 Portfolio is empty.”)
return

```
msg = await update.message.reply_text("📊 Loading portfolio...")
lines = ["📊 *Portfolio*\n"]
total_pnl = 0.0

for ca, h in portfolio.items():
    data = await fetch_token_data(ca)
    if data:
        current_price = float(data.get("priceUsd", 0))
        symbol = data.get("baseToken", {}).get("symbol", h["symbol"])
    else:
        current_price = 0
        symbol = h["symbol"]

    avg_buy = h.get("avg_buy", 0)
    pnl_pct = ((current_price - avg_buy) / avg_buy * 100) if avg_buy > 0 else 0
    emoji   = "🟢" if pnl_pct >= 0 else "🔴"
    total_pnl += pnl_pct

    lines.append(
        f"{emoji} *{symbol}*\n"
        f"  Price: `${current_price:.8f}`\n"
        f"  Avg Buy: `${avg_buy:.8f}`\n"
        f"  PnL: `{pnl_pct:+.1f}%`\n"
        f"  CA: `{ca[:8]}...`\n"
    )

await msg.edit_text("\n".join(lines), parse_mode="Markdown")
```

# ──────────────────────────────────────────────

# COMMAND: /setalert

# ──────────────────────────────────────────────

async def set_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not auth(update): return
if len(context.args) < 2:
await update.message.reply_text(“Usage: `/setalert <CA> <target_price_usd>`”, parse_mode=“Markdown”)
return

```
ca = context.args[0].strip()
try:
    target = float(context.args[1])
except ValueError:
    await update.message.reply_text("❌ Invalid price.")
    return

data = await fetch_token_data(ca)
symbol = data.get("baseToken", {}).get("symbol", ca[:6]) if data else ca[:6]

active_alerts[ca] = {"target_price": target, "symbol": symbol}
await update.message.reply_text(
    f"🔔 Alert set for *{symbol}* at `${target}`",
    parse_mode="Markdown"
)
```

async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not auth(update): return
if not active_alerts:
await update.message.reply_text(“No active alerts.”)
return
lines = [“🔔 *Active Alerts*\n”]
for ca, a in active_alerts.items():
lines.append(f”• *{a[‘symbol’]}* → `${a['target_price']}`”)
await update.message.reply_text(”\n”.join(lines), parse_mode=“Markdown”)

# ──────────────────────────────────────────────

# COMMAND: /snipe

# ──────────────────────────────────────────────

async def snipe(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not auth(update): return
if not context.args:
await update.message.reply_text(“Usage: `/snipe <CA>`”, parse_mode=“Markdown”)
return

```
ca = context.args[0].strip()
if ca in active_snipers:
    await update.message.reply_text("⚡ Already sniping this token.")
    return

await update.message.reply_text(
    f"🎯 *Sniper activated!*\nWatching `{ca[:8]}...` for liquidity...",
    parse_mode="Markdown"
)

task = asyncio.create_task(
    sniper_loop(ca, update.effective_chat.id, context.application)
)
active_snipers[ca] = task
```

async def sniper_loop(ca: str, chat_id: int, app):
“”“Poll Dexscreener every 5s. Buy when liquidity appears.”””
SNIPE_SOL = 0.1  # SOL to snipe with — adjust as needed
while True:
try:
data = await fetch_token_data(ca)
if data:
liq = data.get(“liquidity”, {}).get(“usd”, 0)
if liq > 1000:  # Liquidity threshold
symbol = data.get(“baseToken”, {}).get(“symbol”, ca[:6])
await app.bot.send_message(
chat_id,
f”🚀 *Sniper triggered!*\n{symbol} — Liq: ${liq:,.0f}\nBuying {SNIPE_SOL} SOL…”,
parse_mode=“Markdown”
)
lamports = int(SNIPE_SOL * 1_000_000_000)
quote = await get_jupiter_quote(SOL_MINT, ca, lamports)
if quote:
keypair = get_keypair()
sig = await execute_jupiter_swap(quote, keypair)
await app.bot.send_message(
chat_id,
f”✅ Sniped! Tx: `{sig}`\n[Solscan](https://solscan.io/tx/{sig})”,
parse_mode=“Markdown”,
disable_web_page_preview=True
)
del active_snipers[ca]
return
except Exception as e:
logger.error(f”Sniper error: {e}”)

```
    await asyncio.sleep(5)
```

async def stop_snipers(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not auth(update): return
for ca, task in list(active_snipers.items()):
task.cancel()
del active_snipers[ca]
await update.message.reply_text(“🛑 All snipers stopped.”)

# ──────────────────────────────────────────────

# ALERT BACKGROUND WORKER

# ──────────────────────────────────────────────

async def alert_worker(app):
“”“Background loop that checks price alerts every 30s.”””
while True:
for ca, alert in list(active_alerts.items()):
try:
data = await fetch_token_data(ca)
if data:
current = float(data.get(“priceUsd”, 0))
target  = alert[“target_price”]
if current >= target:
await app.bot.send_message(
AUTHORIZED_USER_ID,
f”🔔 *Alert!* {alert[‘symbol’]} hit `${current:.8f}` (target: `${target}`)”,
parse_mode=“Markdown”
)
del active_alerts[ca]
except Exception as e:
logger.error(f”Alert worker error: {e}”)
await asyncio.sleep(30)

# ──────────────────────────────────────────────

# INLINE BUTTON HANDLER

# ──────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
query = update.callback_query
await query.answer()
data = query.data

```
if data.startswith("buy:"):
    _, ca, sol = data.split(":")
    context.args = [ca, sol]
    update.message = query.message
    await buy(update, context)
```

# ──────────────────────────────────────────────

# MAIN

# ──────────────────────────────────────────────

async def post_init(app):
asyncio.create_task(alert_worker(app))

def main():
app = (
ApplicationBuilder()
.token(BOT_TOKEN)
.post_init(post_init)
.build()
)

```
app.add_handler(CommandHandler("start",     start))
app.add_handler(CommandHandler("price",     price))
app.add_handler(CommandHandler("buy",       buy))
app.add_handler(CommandHandler("sell",      sell))
app.add_handler(CommandHandler("portfolio", show_portfolio))
app.add_handler(CommandHandler("setalert",  set_alert))
app.add_handler(CommandHandler("alerts",    list_alerts))
app.add_handler(CommandHandler("snipe",     snipe))
app.add_handler(CommandHandler("stop",      stop_snipers))
app.add_handler(CallbackQueryHandler(button_handler))

print("🤖 Bot running...")
app.run_polling()
```

if **name** == “**main**”:
main()
