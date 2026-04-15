#!/usr/bin/env python3
"""
DataLine Store - Telegram Bot
Requirements: python-telegram-bot requests
"""

import subprocess, sys
subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "python-telegram-bot==21.6", "--root-user-action=ignore", "-q"])

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

WALLETS = {
    "BTC":        "0",
    "ETH":        "0",
    "USDT_TRC20": "TCGjtfZnsWt3JDccm3Y1uk2QvLmvM3Yt2x",
    "LTC":        "Lak56Y1JhwiW26YwcnXdgMSEMDjSUgp7PB",
}

PRICE_PER_LINE = 5

# Conversation states
CHOOSING_CRYPTO, WAITING_TX, WAITING_BIN, WAITING_COUNTRY = range(4)

# In-memory sessions
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
        if resp.ok:
            return resp.json()
        print(f"API returned {resp.status_code}: {resp.text}")
        return []
    except Exception as e:
        print(f"API error: {e}")
        return []

def search_lines_by_bin(bin_prefix, limit=20):
    try:
        resp = requests.post(
            f"https://api.base44.com/api/apps/{BASE44_APP_ID}/entities/DataLine/filter",
            json={"query": {"status": "available", "bin": {"$regex": f"^{bin_prefix}"}}, "limit": limit, "sort": "-created_date"},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if resp.ok:
            return resp.json()
        return []
    except Exception as e:
        print(f"BIN search error: {e}")
        return []

def search_lines_by_country(country, limit=20):
    try:
        resp = requests.post(
            f"https://api.base44.com/api/apps/{BASE44_APP_ID}/entities/DataLine/filter",
            json={"query": {"status": "available", "country": country.upper()}, "limit": limit, "sort": "-created_date"},
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if resp.ok:
            return resp.json()
        return []
    except Exception as e:
        print(f"Country search error: {e}")
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

# --- HELPERS ---
def build_lines_keyboard(lines):
    kb = []
    for line in lines:
        bin6    = line.get("bin", "??????")
        exp     = f"{line.get('exp_month','??')}/{line.get('exp_year','??')}"
        state   = line.get("state", "")
        country = line.get("country", "")
        label   = f"💳 {bin6}XXXX  {exp}  {state} {country}  — ${PRICE_PER_LINE}"
        kb.append([InlineKeyboardButton(label, callback_data=f"buy_{line['id']}")])
    return kb

# --- HANDLERS ---
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    kb = [
        [InlineKeyboardButton("🛒  Browse Lines",    callback_data="browse")],
        [InlineKeyboardButton("🔍  Search by BIN",   callback_data="search_bin")],
        [InlineKeyboardButton("🌍  Search by Country", callback_data="search_country")],
        [InlineKeyboardButton("💰  How to Pay",      callback_data="howto")],
    ]
    await update.message.reply_text(
        "👋 <b>Welcome to DataLine Store</b>\n\n"
        "💳 Fresh, verified datalines\n"
        f"💵 <b>${PRICE_PER_LINE} per line</b> — Crypto only\n\n"
        "Use the menu below to get started.",
        parse_mode="HTML",
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
    kb = build_lines_keyboard(lines)
    kb.append([InlineKeyboardButton("🔄 Refresh", callback_data="browse")])
    await query.edit_message_text(
        f"🛒 <b>Available Lines</b> ({len(lines)} in stock)\n\nSelect a line to purchase:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def search_bin_prompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔍 <b>BIN Search</b>\n\nType the first 4-6 digits of the BIN you're looking for:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="back_start")]])
    )
    return WAITING_BIN

async def receive_bin_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    bin_prefix = update.message.text.strip().replace(" ", "")
    if not bin_prefix.isdigit() or len(bin_prefix) < 4:
        await update.message.reply_text("⚠️ Please enter at least 4 digits.")
        return WAITING_BIN
    await update.message.reply_text(f"⏳ Searching for BIN <b>{bin_prefix}...</b>", parse_mode="HTML")
    lines = search_lines_by_bin(bin_prefix)
    if not lines:
        kb = [[InlineKeyboardButton("🔄 Try Again", callback_data="search_bin"), InlineKeyboardButton("🛒 Browse All", callback_data="browse")]]
        await update.message.reply_text(f"❌ No available lines found for BIN <b>{bin_prefix}</b>.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
    else:
        kb = build_lines_keyboard(lines)
        kb.append([InlineKeyboardButton("🔄 New Search", callback_data="search_bin"), InlineKeyboardButton("🛒 Browse All", callback_data="browse")])
        await update.message.reply_text(
            f"✅ <b>{len(lines)} lines found</b> for BIN <b>{bin_prefix}</b>:\n\nSelect a line to purchase:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    return ConversationHandler.END

async def search_country_prompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🌍 <b>Country Search</b>\n\nType the country code (e.g. <b>US</b>, <b>UK</b>, <b>CA</b>, <b>AU</b>):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="back_start")]])
    )
    return WAITING_COUNTRY

async def receive_country_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    country = update.message.text.strip().upper()
    if len(country) < 2:
        await update.message.reply_text("⚠️ Please enter a valid country code (e.g. US, UK, CA).")
        return WAITING_COUNTRY
    await update.message.reply_text(f"⏳ Searching for lines in <b>{country}...</b>", parse_mode="HTML")
    lines = search_lines_by_country(country)
    if not lines:
        kb = [[InlineKeyboardButton("🔄 Try Again", callback_data="search_country"), InlineKeyboardButton("🛒 Browse All", callback_data="browse")]]
        await update.message.reply_text(f"❌ No available lines found for country <b>{country}</b>.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
    else:
        kb = build_lines_keyboard(lines)
        kb.append([InlineKeyboardButton("🔄 New Search", callback_data="search_country"), InlineKeyboardButton("🛒 Browse All", callback_data="browse")])
        await update.message.reply_text(
            f"✅ <b>{len(lines)} lines found</b> in <b>{country}</b>:\n\nSelect a line to purchase:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    return ConversationHandler.END

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
        f"💰 <b>Choose Payment Method</b>\n\nAmount: <b>${PRICE_PER_LINE} USD</b>",
        parse_mode="HTML",
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
        f"📤 <b>Send Payment</b>\n\n"
        f"Amount: <b>${PRICE_PER_LINE} USD</b> in {crypto}\n\n"
        f"Wallet:\n<code>{wallet}</code>\n\n"
        "After sending, reply with your <b>transaction hash</b> (TX ID) to confirm.",
        parse_mode="HTML"
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
        uname = update.effective_user.username or str(uid)
        await ctx.bot.send_message(
            ADMIN_ID,
            f"🔔 <b>New Order</b>\n"
            f"Line: <code>{line_id}</code>\n"
            f"Crypto: {crypto}\n"
            f"TX: <code>{tx_hash}</code>\n"
            f"Amount: ${PRICE_PER_LINE} USD\n"
            f"User: @{uname}",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Admin notify error: {e}")
    await update.message.reply_text(
        "✅ <b>Payment Received!</b>\n\n"
        "Your TX hash has been submitted. "
        "Our team will verify and send your dataline within 30 minutes.\n\n"
        "Thank you for your purchase! 🙏",
        parse_mode="HTML"
    )
    return ConversationHandler.END

async def howto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📖 <b>How to Buy</b>\n\n"
        "1. Tap <b>Browse Lines</b> and pick a dataline\n"
        "2. Choose your crypto (BTC/ETH/USDT/LTC)\n"
        "3. Send the exact amount to the wallet shown\n"
        "4. Paste your TX hash in chat\n"
        "5. Admin confirms and sends you the full line\n\n"
        "Delivery: within 30 minutes after confirmation.",
        parse_mode="HTML",
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
        "👋 <b>Welcome to DataLine Store</b>\n\n"
        f"💵 <b>${PRICE_PER_LINE} per line</b> — Crypto only",
        parse_mode="HTML",
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
        f"✅ <b>Your DataLine is Ready!</b>\n\n"
        f"Order: <code>{order_id}</code>\n\n"
        f"<code>{raw_line}</code>\n\n"
        "Keep this safe. Do not share.",
        parse_mode="HTML"
    )
    await update.message.reply_text("✅ Delivered!")

# --- MAIN ---
def main():
    print("🤖 Starting bot...")
    app = Application.builder().token(BOT_TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(choose_crypto, pattern=r"^crypto_")],
        states={WAITING_TX: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_tx)]},
        fallbacks=[CommandHandler("start", start)],
    )
    bin_search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(search_bin_prompt, pattern="^search_bin$")],
        states={WAITING_BIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_bin_search)]},
        fallbacks=[CommandHandler("start", start)],
    )
    country_search_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(search_country_prompt, pattern="^search_country$")],
        states={WAITING_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_country_search)]},
        fallbacks=[CommandHandler("start", start)],
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("deliver", admin_deliver))
    app.add_handler(CallbackQueryHandler(browse,     pattern="^browse$"))
    app.add_handler(CallbackQueryHandler(buy_line,   pattern=r"^buy_"))
    app.add_handler(CallbackQueryHandler(howto,      pattern="^howto$"))
    app.add_handler(CallbackQueryHandler(back_start, pattern="^back_start$"))
    app.add_handler(conv)
    app.add_handler(bin_search_conv)
    app.add_handler(country_search_conv)
    async def on_startup(application):
        await application.bot.send_message(
            chat_id=ADMIN_ID,
            text="🟢 <b>Bot is now online!</b>\n\nDataLine Store bot has started successfully.",
            parse_mode="HTML"
        )

    app.post_init = on_startup
    print("🤖 Bot is running!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
