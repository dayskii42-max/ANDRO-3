#!/usr/bin/env python3
"""
DataLine Store - Telegram Bot
Deploy on Railway, Render, or any VPS
Requirements: pip install python-telegram-bot requests
"""

import os
import json
import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# --- CONFIG ---
BOT_TOKEN   = "7687131149:AAGZwUSOtsqj4JycwgOrHYmjMJOrtzwCjIk"
ADMIN_ID    = 8798542436
STORE_URL   = "https://preview-sandbox--69e00594222f3c79030a6942.base44.app"

# Crypto wallets
WALLETS = {
    "BTC":        "0",
    "ETH":        "0",
    "USDT_TRC20": "TCGjtfZnsWt3JDccm3Y1uk2QvLmvM3Yt2x",
    "LTC":        "Lak56Y1JhwiW26YwcnXdgMSEMDjSUgp7PB",
}

PRICE_PER_LINE = 5

# Conversation states
CHOOSING_CRYPTO, WAITING_TX = range(2)

# In-memory sessions (use Redis for production)
user_sessions = {}

# --- BASE44 API ---
BASE44_APP_ID = "69e00594222f3c79030a6942"

def get_available_lines(limit=20):
    try:
        resp = requests.post(
            f"https://api.base44.com/api/apps/{BASE44_APP_ID}/entities/DataLine/filter",
            json={"query": {"status": "available"}, "limit": limit, "sort": "-created_date"},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        return resp.json() if resp.ok else []
    except Exception as e:
        print(f"API error: {e}")
        return []

def reserve_line(line_id):
    try:
        requests.put(
            f"https://api.base44.com/api/apps/{BASE44_APP_ID}/entities/DataLine/{line_id}",
            json={"status": "reserved"},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
    except Exception as e:
        print(f"Reserve error: {e}")

def create_order(line_id, crypto, tx_hash, wallet):
    try:
        requests.post(
            f"https://api.base44.com/api/apps/{BASE44_APP_ID}/entities/Order",
            json={
                "dataline_id": line_id,
                "crypto_type": crypto,
                "amount_usd": PRICE_PER_LINE,
                "tx_hash": tx_hash,
                "status": "payment_sent",
                "wallet_address_used": wallet,
            },
            headers={"Content-Type": "application/json"},
            timeout=10
        )
    except Exception as e:
        print(f"Order error: {e}")

# --- HANDLERS ---
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🛒  Browse Lines", callback_data="browse")],
        [InlineKeyboardButton("💰  How to Pay",   callback_data="howto")],
        [InlineKeyboardButton("📞  Support",       url="https://t.me/YourSupportUsername")],
    ]
    await update.message.reply_text(
        "👋 *Welcome to DataLine Store*\n\n"
        "💳 Fresh, verified datalines\n"
        f"💵 5 per line — Crypto only\n\n"
        "Use the menu below to get started\.",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def browse(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Loading available lines...")
    lines = get_available_lines(20)
    if not lines:
        await query.edit_message_text("❌ No lines available right now. Check back soon!")
        return
    kb = []
    for line in lines:
        bin6    = line.get("bin", "??????")
        exp     = f"{line.get('exp_month','??')}/{line.get('exp_year','??')}"
        state   = line.get("state", "")
        country = line.get("country", "")
        label   = f"💳 {bin6}XXXX  {exp}  {state} {country}  — $5"
        kb.append([InlineKeyboardButton(label, callback_data=f"buy_{line['id']}" )])
    kb.append([InlineKeyboardButton("🔄 Refresh", callback_data="browse")])
    await query.edit_message_text(
        f"🛒 *Available Lines* ({len(lines)} in stock)\n\nSelect a line to purchase:",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def buy_line(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    line_id = query.data.replace("buy_", "")
    user_sessions[query.from_user.id] = {"line_id": line_id}
    kb = [
        [InlineKeyboardButton("₿  Bitcoin (BTC)",   callback_data=f"crypto_BTC_{line_id}")],
        [InlineKeyboardButton("Ξ  Ethereum (ETH)",  callback_data=f"crypto_ETH_{line_id}")],
        [InlineKeyboardButton("₮  USDT TRC20",      callback_data=f"crypto_USDT_TRC20_{line_id}")],
        [InlineKeyboardButton("Ł  Litecoin (LTC)",  callback_data=f"crypto_LTC_{line_id}")],
        [InlineKeyboardButton("« Back",             callback_data="browse")],
    ]
    await query.edit_message_text(
        f"💰 *Choose Payment Method*\n\nAmount: *5 USD*",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def choose_crypto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if "USDT_TRC20" in query.data:
        crypto  = "USDT_TRC20"
        line_id = query.data.replace("crypto_USDT_TRC20_", "")
    else:
        _, crypto, line_id = query.data.split("_", 2)
    wallet = WALLETS.get(crypto, "NOT_CONFIGURED")
    user_sessions[query.from_user.id] = {"line_id": line_id, "crypto": crypto}
    reserve_line(line_id)
    await query.edit_message_text(
        f"📤 *Send Payment*\n\n"
        f"Amount: *{PRICE_PER_LINE} USD* in {crypto}\n\n"
        f"Wallet:\n`{wallet}`\n\n"
        f"After sending, reply with your *transaction hash* (TX ID) to confirm.",
        parse_mode="MarkdownV2"
    )
    return WAITING_TX

async def receive_tx(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid     = update.effective_user.id
    tx_hash = update.message.text.strip()
    session = user_sessions.get(uid, {})
    if not session.get("line_id"):
        await update.message.reply_text("Session expired. Use /start to begin again.")
        return ConversationHandler.END
    line_id = session["line_id"]
    crypto  = session.get("crypto", "BTC")
    wallet  = WALLETS.get(crypto, "")
    create_order(line_id, crypto, tx_hash, wallet)
    user_sessions.pop(uid, None)
    try:
        await ctx.bot.send_message(
            ADMIN_ID,
            f"🔔 *New Order*\n"
            f"Line: `{line_id}`\n"
            f"Crypto: {crypto}\n"
            f"TX: `{tx_hash}`\n"
            f"Amount: {PRICE_PER_LINE} USD\n"
            f"User: @{update.effective_user.username or uid}",
            parse_mode="MarkdownV2"
        )
    except Exception:
        pass
    await update.message.reply_text(
        "✅ *Payment Received!*\n\n"
        "Your TX hash has been submitted. "
        "Our team will verify and send your dataline within 30 minutes.\n\n"
        "Thank you for your purchase! 🙏",
        parse_mode="MarkdownV2"
    )
    return ConversationHandler.END

async def howto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📖 *How to Buy*\n\n"
        "1. Tap *Browse Lines* and pick a dataline\n"
        "2. Choose your crypto (BTC/ETH/USDT/LTC)\n"
        "3. Send the exact amount to the wallet shown\n"
        "4. Paste your TX hash in chat\n"
        "5. Admin confirms and sends you the full line\n\n"
        "Delivery: within 30 minutes after confirmation.",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="back_start")]])
    )

async def back_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [
        [InlineKeyboardButton("🛒  Browse Lines", callback_data="browse")],
        [InlineKeyboardButton("💰  How to Pay",   callback_data="howto")],
    ]
    await query.edit_message_text(
        "👋 *Welcome to DataLine Store*\n\n"
        "💵 $5 per line — Crypto only",
        parse_mode="MarkdownV2",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def admin_deliver(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    parts = update.message.text.split(" ", 3)
    if len(parts) < 4:
        await update.message.reply_text("Usage: /deliver <order_id> <user_id> <raw_line>")
        return
    _, order_id, user_id, raw_line = parts
    await ctx.bot.send_message(
        int(user_id),
        f"✅ *Your DataLine is Ready!*\n\n"
        f"Order: `{order_id}`\n\n"
        f"`{raw_line}`\n\n"
        "Keep this safe. Do not share.",
        parse_mode="MarkdownV2"
    )
    await update.message.reply_text("✅ Delivered!")

# --- MAIN ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(choose_crypto, pattern=r"^crypto_")],
        states={WAITING_TX: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_tx)]},
        fallbacks=[CommandHandler("start", start)],
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("deliver", admin_deliver))
    app.add_handler(CallbackQueryHandler(browse,     pattern="^browse$"))
    app.add_handler(CallbackQueryHandler(buy_line,   pattern=r"^buy_"))
    app.add_handler(CallbackQueryHandler(howto,      pattern="^howto$"))
    app.add_handler(CallbackQueryHandler(back_start, pattern="^back_start$"))
    app.add_handler(conv)
    print("🤖 Bot is running...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()