#!/usr/bin/env python3
"""
DataLine Store - Telegram Bot (Balance-Only Purchase, $15 min top-up)
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
STORE_URL   = "https://telegram.me/datalaunch_bot"

WALLETS = {
    "BTC":        "0",
    "ETH":        "0",
    "USDT_TRC20": "TCGjtfZnsWt3JDccm3Y1uk2QvLmvM3Yt2x",
    "LTC":        "Lak56Y1JhwiW26YwcnXdgMSEMDjSUgp7PB",
}

PRICE_PER_LINE  = 5
MIN_TOPUP       = 15  # Minimum top-up amount in USD

# Conversation states
WAITING_BIN, WAITING_COUNTRY = range(2)
TOPUP_CHOOSING_CRYPTO, TOPUP_CHOOSING_AMOUNT, TOPUP_CUSTOM_AMOUNT, TOPUP_WAITING_TX = range(2, 6)

# In-memory sessions
user_sessions = {}

# --- BACKEND API ---
API_URL = "https://loud-cipher-trade-core.base44.app/api/functions/getBotData"
HEADERS = {"Content-Type": "application/json"}
BOT_SECRET = "ANDRO"

def call_api(payload):
    try:
        payload["secret"] = BOT_SECRET
        resp = requests.post(API_URL, json=payload, headers=HEADERS, timeout=10)
        if resp.ok:
            return resp.json()
        print(f"API error {resp.status_code}: {resp.text}")
        return None
    except Exception as e:
        print(f"API error: {e}")
        return None

def get_available_lines(limit=20):
    result = call_api({"action": "get_available", "query": {"limit": limit}})
    return result if isinstance(result, list) else []

def search_lines_by_bin(bin_prefix, limit=20):
    result = call_api({"action": "search_bin", "query": {"bin_prefix": bin_prefix}})
    return result if isinstance(result, list) else []

def search_lines_by_country(country, limit=20):
    result = call_api({"action": "search_country", "query": {"country": country}})
    return result if isinstance(result, list) else []

def get_balance(user_id):
    result = call_api({"action": "get_balance", "telegram_user_id": str(user_id)})
    return result.get("balance_usd", 0) if result else 0

def submit_topup(user_id, username, crypto, amount, tx_hash, wallet):
    call_api({
        "action": "submit_topup",
        "telegram_user_id": str(user_id),
        "telegram_username": username or "",
        "crypto_type": crypto,
        "amount_usd": amount,
        "tx_hash": tx_hash,
        "wallet_address": wallet,
    })

def buy_with_balance(user_id, line_id):
    return call_api({
        "action": "buy_with_balance",
        "telegram_user_id": str(user_id),
        "line_id": line_id,
    })

# --- HELPERS ---
def fmt(x):
    return f"{x:.2f}"

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
    uid = update.effective_user.id
    balance = get_balance(uid)
    kb = [
        [InlineKeyboardButton("🛒  Browse Lines",      callback_data="browse")],
        [InlineKeyboardButton("🔍  Search by BIN",     callback_data="search_bin")],
        [InlineKeyboardButton("🌍  Search by Country", callback_data="search_country")],
        [InlineKeyboardButton("💰  My Balance: $" + fmt(balance), callback_data="balance_menu")],
        [InlineKeyboardButton("➕  Top Up Balance",    callback_data="topup_start")],
        [InlineKeyboardButton("ℹ️  How to Buy",         callback_data="howto")],
    ]
    await update.message.reply_text(
        "👋 <b>Welcome to DataLine Store</b>\n\n"
        "💳 Fresh, verified datalines\n"
        f"💵 <b>${PRICE_PER_LINE} per line</b>\n\n"
        "⚡ <b>Balance-based purchases only.</b>\n"
        f"Top up your balance (min <b>${MIN_TOPUP}</b>) and buy instantly.\n\n"
        "Use the menu below to get started.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def balance_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    balance = get_balance(uid)
    kb = [
        [InlineKeyboardButton("➕ Top Up Balance", callback_data="topup_start")],
        [InlineKeyboardButton("🛒 Browse & Buy",   callback_data="browse")],
        [InlineKeyboardButton("« Back",            callback_data="back_start")],
    ]
    await query.edit_message_text(
        "💰 <b>Your Balance</b>\n\n"
        "Available: <b>$" + fmt(balance) + " USD</b>\n\n"
        f"Minimum top-up: <b>${MIN_TOPUP}</b>\n"
        "Funds are credited automatically after blockchain confirmation.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb)
    )

# ── TOP UP FLOW ──────────────────────────────────────────────────────────────
async def topup_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    kb = [
        [InlineKeyboardButton("₿ Bitcoin (BTC)",   callback_data="tc_BTC")],
        [InlineKeyboardButton("Ξ Ethereum (ETH)",  callback_data="tc_ETH")],
        [InlineKeyboardButton("₮ USDT TRC20",      callback_data="tc_USDT_TRC20")],
        [InlineKeyboardButton("Ł Litecoin (LTC)",  callback_data="tc_LTC")],
        [InlineKeyboardButton("« Back",            callback_data="back_start")],
    ]
    await query.edit_message_text(
        "➕ <b>Top Up Balance</b>\n\n"
        f"Minimum top-up: <b>${MIN_TOPUP} USD</b>\n\n"
        "Choose your crypto:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return TOPUP_CHOOSING_CRYPTO

async def topup_choose_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    crypto = query.data.replace("tc_", "")
    user_sessions[query.from_user.id] = {"topup_crypto": crypto}
    kb = [
        [InlineKeyboardButton("$15",  callback_data="ta_15"),
         InlineKeyboardButton("$25",  callback_data="ta_25")],
        [InlineKeyboardButton("$50",  callback_data="ta_50"),
         InlineKeyboardButton("$100", callback_data="ta_100")],
        [InlineKeyboardButton("💰 Custom Amount", callback_data="ta_custom")],
        [InlineKeyboardButton("« Back", callback_data="topup_start")],
    ]
    await query.edit_message_text(
        f"➕ <b>Top Up via {crypto}</b>\n\n"
        f"Minimum: <b>${MIN_TOPUP}</b>\n\n"
        "Choose amount:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb)
    )
    return TOPUP_CHOOSING_AMOUNT

async def topup_custom_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        f"➕ <b>Enter Custom Amount</b>\n\n"
        f"Minimum: <b>${MIN_TOPUP}</b>\n\n"
        "Type the amount in USD (e.g., 20, 75, 200):",
        parse_mode="HTML"
    )
    return TOPUP_CUSTOM_AMOUNT

async def topup_receive_custom_amount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    try:
        amount = float(update.message.text.strip())
        if amount < MIN_TOPUP:
            await update.message.reply_text(f"⚠️ Minimum amount is <b>${MIN_TOPUP}</b>.", parse_mode="HTML")
            return TOPUP_CUSTOM_AMOUNT
        session = user_sessions.get(uid, {})
        crypto = session.get("topup_crypto", "BTC")
        wallet = WALLETS.get(crypto, "NOT_CONFIGURED")
        user_sessions[uid] = {**session, "topup_amount": amount, "topup_wallet": wallet}
        formatted_amount = f"{amount:.2f}"
        await update.message.reply_text(
            f"➕ <b>Send ${formatted_amount} in {crypto}</b>\n\n"
            f"Wallet:\n<code>{wallet}</code>\n\n"
            "After sending, reply with your <b>transaction hash (TX ID)</b>.\n"
            "Your balance will be credited automatically after blockchain confirmation.",
            parse_mode="HTML"
        )
        return TOPUP_WAITING_TX
    except ValueError:
        await update.message.reply_text("⚠️ Please enter a valid number (e.g., 20, 50.50).")
        return TOPUP_CUSTOM_AMOUNT

async def topup_show_wallet(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    amount = int(query.data.replace("ta_", ""))
    uid = query.from_user.id
    session = user_sessions.get(uid, {})
    crypto = session.get("topup_crypto", "BTC")
    wallet = WALLETS.get(crypto, "NOT_CONFIGURED")
    user_sessions[uid] = {**session, "topup_amount": amount, "topup_wallet": wallet}
    await query.edit_message_text(
        f"➕ <b>Send ${amount} in {crypto}</b>\n\n"
        f"Wallet:\n<code>{wallet}</code>\n\n"
        "After sending, reply with your <b>transaction hash (TX ID)</b>.\n"
        "Your balance will be credited automatically after blockchain confirmation.",
        parse_mode="HTML"
    )
    return TOPUP_WAITING_TX

async def topup_receive_tx(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    tx_hash = update.message.text.strip()
    session = user_sessions.get(uid, {})
    crypto = session.get("topup_crypto", "BTC")
    amount = session.get("topup_amount", 0)
    wallet = session.get("topup_wallet", "")
    uname  = update.effective_user.username or str(uid)
    if not amount or amount < MIN_TOPUP:
        await update.message.reply_text(f"❌ Invalid amount. Minimum is <b>${MIN_TOPUP}</b>.", parse_mode="HTML")
        return TOPUP_WAITING_TX
    submit_topup(uid, uname, crypto, amount, tx_hash, wallet)
    user_sessions.pop(uid, None)
    try:
        await ctx.bot.send_message(
            ADMIN_ID,
            f"🔔 <b>New Top-Up Request</b>\n"
            f"User: @{uname} ({uid})\n"
            f"Crypto: {crypto}\n"
            f"Amount: ${amount} USD\n"
            f"TX: <code>{tx_hash}</code>",
            parse_mode="HTML"
        )
    except Exception as e:
        print(f"Admin notify error: {e}")
    await update.message.reply_text(
        "✅ <b>Top-up submitted!</b>\n\n"
        f"TX: <code>{tx_hash}</code>\n\n"
        "Your balance will be credited automatically after blockchain confirmation (usually a few minutes).\n"
        "Use /balance to check your balance.",
        parse_mode="HTML"
    )
    return ConversationHandler.END

# ── BROWSE / BUY FLOW (Balance only) ─────────────────────────────────────────
async def browse(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ Loading available lines...")
    lines = get_available_lines(20)
    if not lines:
        kb = [[InlineKeyboardButton("🔄 Refresh", callback_data="browse"), InlineKeyboardButton("« Back", callback_data="back_start")]]
        await query.edit_message_text("❌ No lines available right now. Check back soon!", reply_markup=InlineKeyboardMarkup(kb))
        return
    kb = build_lines_keyboard(lines)
    kb.append([InlineKeyboardButton("🔄 Refresh", callback_data="browse")])
    await query.edit_message_text(
        f"🛒 <b>Available Lines</b> ({len(lines)} in stock)\n\nSelect a line to purchase with your balance:",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def search_bin_prompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🔍 <b>BIN Search</b>\n\nType the first 4-6 digits:",
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
        await update.message.reply_text(f"❌ No lines found for BIN <b>{bin_prefix}</b>.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
    else:
        kb = build_lines_keyboard(lines)
        kb.append([InlineKeyboardButton("🔄 New Search", callback_data="search_bin"), InlineKeyboardButton("🛒 Browse All", callback_data="browse")])
        await update.message.reply_text(
            f"✅ <b>{len(lines)} lines found</b> for BIN <b>{bin_prefix}</b>:\n\nSelect a line:",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb)
        )
    return ConversationHandler.END

async def search_country_prompt(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🌍 <b>Country Search</b>\n\nType the country code (e.g. <b>US</b>, <b>UK</b>, <b>CA</b>):",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("« Back", callback_data="back_start")]])
    )
    return WAITING_COUNTRY

async def receive_country_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    country = update.message.text.strip().upper()
    if len(country) < 2:
        await update.message.reply_text("⚠️ Please enter a valid country code (e.g. US, UK, CA).")
        return WAITING_COUNTRY
    await update.message.reply_text(f"⏳ Searching lines in <b>{country}...</b>", parse_mode="HTML")
    lines = search_lines_by_country(country)
    if not lines:
        kb = [[InlineKeyboardButton("🔄 Try Again", callback_data="search_country"), InlineKeyboardButton("🛒 Browse All", callback_data="browse")]]
        await update.message.reply_text(f"❌ No lines found for <b>{country}</b>.", parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb))
    else:
        kb = build_lines_keyboard(lines)
        kb.append([InlineKeyboardButton("🔄 New Search", callback_data="search_country"), InlineKeyboardButton("🛒 Browse All", callback_data="browse")])
        await update.message.reply_text(
            f"✅ <b>{len(lines)} lines found</b> in <b>{country}</b>:\n\nSelect a line:",
            parse_mode="HTML", reply_markup=InlineKeyboardMarkup(kb)
        )
    return ConversationHandler.END

async def buy_line(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    line_id = query.data.replace("buy_", "")
    uid = query.from_user.id
    balance = get_balance(uid)

    if balance >= PRICE_PER_LINE:
        kb = [
            [InlineKeyboardButton("⚡ Buy Now ($" + fmt(balance) + " balance)", callback_data=f"bal_{line_id}")],
            [InlineKeyboardButton("« Back", callback_data="browse")],
        ]
        await query.edit_message_text(
            f"💳 <b>Confirm Purchase</b>\n\n"
            f"Price: <b>${PRICE_PER_LINE}</b>\n"
            "Your balance: <b>$" + fmt(balance) + "</b>\n\n"
            "Tap below to buy instantly:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb)
        )
    else:
        needed = PRICE_PER_LINE - balance
        kb = [
            [InlineKeyboardButton("➕ Top Up Balance", callback_data="topup_start")],
            [InlineKeyboardButton("« Back",            callback_data="browse")],
        ]
        await query.edit_message_text(
            f"❌ <b>Insufficient Balance</b>\n\n"
            f"Price: <b>${PRICE_PER_LINE}</b>\n"
            "Your balance: <b>$" + fmt(balance) + "</b>\n"
            "Needed: <b>$" + fmt(needed) + " more</b>\n\n"
            f"Top up your balance (min <b>${MIN_TOPUP}</b>) to purchase.",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(kb)
        )

async def buy_with_balance_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    line_id = query.data.replace("bal_", "")
    uid = query.from_user.id
    await query.edit_message_text("⏳ Processing purchase...")
    result = buy_with_balance(uid, line_id)
    if not result:
        await query.edit_message_text("❌ Purchase failed. Please try again or contact support.")
        return
    if result.get("error"):
        err = result["error"]
        if err == "Insufficient balance":
            bal = result.get("balance", 0)
            price = result.get("price", PRICE_PER_LINE)
            await query.edit_message_text(
                "❌ Insufficient balance ($" + fmt(bal) + " / $" + str(price) + ")\nTop up and try again.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Top Up", callback_data="topup_start")]])
            )
        else:
            await query.edit_message_text(f"❌ Error: {err}")
        return
    raw_line = result.get("raw_line", "")
    new_balance = result.get("new_balance", 0)
    await query.edit_message_text(
        "✅ <b>Purchase Complete!</b>\n\n"
        f"<code>{raw_line}</code>\n\n"
        "Remaining balance: <b>$" + fmt(new_balance) + "</b>\n\n"
        "Keep this safe. Do not share.",
        parse_mode="HTML"
    )

async def balance_command(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    balance = get_balance(uid)
    kb = [[InlineKeyboardButton("➕ Top Up", callback_data="topup_start"), InlineKeyboardButton("🛒 Browse", callback_data="browse")]]
    await update.message.reply_text(
        "💰 <b>Your Balance</b>\n\nAvailable: <b>$" + fmt(balance) + " USD</b>",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(kb)
    )

async def howto(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "📖 <b>How to Buy</b>\n\n"
        "This store uses a <b>balance system</b> — no direct payment at checkout.\n\n"
        "<b>Step 1 — Top Up:</b>\n"
        f"Send crypto to top up your balance (min <b>${MIN_TOPUP}</b>).\n"
        "Your balance is credited automatically after blockchain confirmation.\n\n"
        "<b>Step 2 — Browse:</b>\n"
        "Browse available datalines and select one.\n\n"
        "<b>Step 3 — Buy Instantly:</b>\n"
        "Click ⚡ Buy Now — delivered immediately from your balance.\n\n"
        "✅ No waiting, no manual steps.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("➕ Top Up Now", callback_data="topup_start"), InlineKeyboardButton("« Back", callback_data="back_start")]])
    )

async def back_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = query.from_user.id
    balance = get_balance(uid)
    kb = [
        [InlineKeyboardButton("🛒  Browse Lines",      callback_data="browse")],
        [InlineKeyboardButton("🔍  Search by BIN",     callback_data="search_bin")],
        [InlineKeyboardButton("🌍  Search by Country", callback_data="search_country")],
        [InlineKeyboardButton("💰  My Balance: $" + fmt(balance), callback_data="balance_menu")],
        [InlineKeyboardButton("➕  Top Up Balance",    callback_data="topup_start")],
        [InlineKeyboardButton("ℹ️  How to Buy",         callback_data="howto")],
    ]
    await query.edit_message_text(
        "👋 <b>DataLine Store</b>\n\n"
        f"💵 <b>${PRICE_PER_LINE} per line</b>\n"
        "⚡ Balance purchases only",
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

    # Top-up conversation
    topup_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(topup_start, pattern="^topup_start$")],
        states={
            TOPUP_CHOOSING_CRYPTO:  [CallbackQueryHandler(topup_choose_amount, pattern=r"^tc_")],
            TOPUP_CHOOSING_AMOUNT:  [CallbackQueryHandler(topup_show_wallet, pattern=r"^ta_(?!custom)"), CallbackQueryHandler(topup_custom_amount, pattern=r"^ta_custom$")],
            TOPUP_CUSTOM_AMOUNT:    [MessageHandler(filters.TEXT & ~filters.COMMAND, topup_receive_custom_amount)],
            TOPUP_WAITING_TX:       [MessageHandler(filters.TEXT & ~filters.COMMAND, topup_receive_tx)],
        },
        fallbacks=[CommandHandler("start", start)],
        per_message=True,
    )

    bin_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(search_bin_prompt, pattern="^search_bin$")],
        states={WAITING_BIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_bin_search)]},
        fallbacks=[CommandHandler("start", start)],
        per_message=True,
    )

    country_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(search_country_prompt, pattern="^search_country$")],
        states={WAITING_COUNTRY: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_country_search)]},
        fallbacks=[CommandHandler("start", start)],
        per_message=True,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance_command))
    app.add_handler(CommandHandler("deliver", admin_deliver))
    app.add_handler(CallbackQueryHandler(browse,                  pattern="^browse$"))
    app.add_handler(CallbackQueryHandler(buy_line,                pattern=r"^buy_"))
    app.add_handler(CallbackQueryHandler(buy_with_balance_handler,pattern=r"^bal_"))
    app.add_handler(CallbackQueryHandler(balance_menu,            pattern="^balance_menu$"))
    app.add_handler(CallbackQueryHandler(howto,                   pattern="^howto$"))
    app.add_handler(CallbackQueryHandler(back_start,              pattern="^back_start$"))
    app.add_handler(topup_conv)
    app.add_handler(bin_conv)
    app.add_handler(country_conv)

    async def on_startup(application):
        await application.bot.send_message(
            chat_id=ADMIN_ID,
            text="🟢 <b>Bot is now online!</b>\n\nDataLine Store bot started.",
            parse_mode="HTML"
        )

    app.post_init = on_startup
    print("🤖 Bot is running!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
