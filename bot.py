import logging
import os
import io
import asyncio
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)
import barcode
from barcode.writer import ImageWriter
from PIL import Image

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# UPDATED: Now looking for a unique key called 'BARCODE_BOT_TOKEN'
BOT_TOKEN = os.environ.get('BARCODE_BOT_TOKEN')

# Modes
MODE_WAIT_DATA = "wait_data"

# Barcode types with their specs
BARCODE_TYPES = [
    {
        "key": "ean13",
        "label": "🏷 EAN-13 (retail products)",
        "code": "ean13",
        "format": "Exactly *12 digits* (checksum auto-added).\nExample: `978020137962`",
        "validator": lambda s: s.isdigit() and len(s) == 12,
    },
    {
        "key": "ean8",
        "label": "🏷 EAN-8 (short retail)",
        "code": "ean8",
        "format": "Exactly *7 digits* (checksum auto-added).\nExample: `9638507`",
        "validator": lambda s: s.isdigit() and len(s) == 7,
    },
    {
        "key": "upca",
        "label": "🛒 UPC-A (US/Canada retail)",
        "code": "upca",
        "format": "Exactly *11 digits* (checksum auto-added).\nExample: `03600029145`",
        "validator": lambda s: s.isdigit() and len(s) == 11,
    },
    {
        "key": "code128",
        "label": "🔠 Code 128 (any text)",
        "code": "code128",
        "format": "Any ASCII text (letters, digits, symbols).\nExample: `HELLO-2025`",
        "validator": lambda s: 1 <= len(s) <= 80,
    },
    {
        "key": "code39",
        "label": "🔡 Code 39 (alphanumeric)",
        "code": "code39",
        "format": "UPPERCASE letters, digits, and `-. $/+%`.\nExample: `PRODUCT-001`",
        "validator": lambda s: all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-. $/+%" for c in s.upper()) and len(s) <= 50,
    },
    {
        "key": "isbn13",
        "label": "📚 ISBN-13 (books)",
        "code": "isbn13",
        "format": "Exactly *12 digits* (checksum auto-added).\nExample: `978014028329`",
        "validator": lambda s: s.isdigit() and len(s) == 12,
    },
    {
        "key": "itf",
        "label": "📦 ITF (Interleaved 2 of 5)",
        "code": "itf",
        "format": "Even number of digits.\nExample: `1234567890`",
        "validator": lambda s: s.isdigit() and len(s) >= 4 and len(s) % 2 == 0,
    },
]


# ---------- Helpers ----------

def main_menu_markup() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("⚡ Create Barcode", callback_data="menu_create")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="menu_help")],
    ]
    return InlineKeyboardMarkup(keyboard)


def types_markup() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(t["label"], callback_data=f"bt_{t['key']}")] for t in BARCODE_TYPES]
    rows.append([InlineKeyboardButton("🏠 Main Menu", callback_data="menu_home")])
    return InlineKeyboardMarkup(rows)


def reset_user_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in ('mode', 'bc_type'):
        context.user_data.pop(key, None)


def get_type(key: str):
    for t in BARCODE_TYPES:
        if t["key"] == key:
            return t
    return None


# ---------- Commands ----------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"User {user.id} started the bot")
    reset_user_state(context)

    welcome = (
        "👋 *Welcome to Barcode Generator Bot!*\n\n"
        "I create professional barcodes in seconds 📊\n\n"
        "✨ *7 supported formats:*\n"
        "• 🏷 EAN-13 / EAN-8\n"
        "• 🛒 UPC-A\n"
        "• 🔠 Code 128 / Code 39\n"
        "• 📚 ISBN-13\n"
        "• 📦 ITF\n\n"
        "Output: hi-res PNG ready to print\n\n"
        "Tap below to begin:"
    )
    await update.message.reply_text(welcome, reply_markup=main_menu_markup(), parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "ℹ️ *How to use*\n\n"
        "1. Tap ⚡ *Create Barcode*\n"
        "2. Pick a barcode format\n"
        "3. Send the data (digits or text)\n"
        "4. Get the barcode!\n\n"
        "💡 *Quick guide:*\n"
        "• `EAN-13` → retail products worldwide\n"
        "• `UPC-A` → US retail products\n"
        "• `Code 128` → any text, common in logistics\n"
        "• `Code 39` → industrial, uppercase\n"
        "• `ISBN` → books\n\n"
        "Use /cancel anytime to reset."
    )
    if update.message:
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=main_menu_markup())
    else:
        await update.callback_query.edit_message_text(
            text, parse_mode='Markdown', reply_markup=main_menu_markup()
        )


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reset_user_state(context)
    await update.message.reply_text(
        "❌ Cancelled. Use /start to begin again.",
        reply_markup=main_menu_markup(),
    )


# ---------- Menu callbacks ----------

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "menu_home":
        reset_user_state(context)
        await query.edit_message_text(
            "🏠 *Main Menu*\nChoose an option below:",
            reply_markup=main_menu_markup(),
            parse_mode='Markdown',
        )

    elif data == "menu_help":
        await help_command(update, context)

    elif data == "menu_create":
        await query.edit_message_text(
            "⚡ *Create Barcode*\n\nPick a barcode format:",
            reply_markup=types_markup(),
            parse_mode='Markdown',
        )

    elif data.startswith("bt_"):
        bt_key = data.split("_", 1)[1]
        t = get_type(bt_key)
        if not t:
            await query.edit_message_text("⚠️ Unknown type.", reply_markup=main_menu_markup())
            return
        context.user_data['bc_type'] = bt_key
        context.user_data['mode'] = MODE_WAIT_DATA
        await query.edit_message_text(
            f"📥 *{t['label']}*\n\n"
            f"Send the data to encode:\n\n{t['format']}\n\n"
            "_Use /cancel to abort._",
            parse_mode='Markdown',
        )


# ---------- Text handler ----------

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get('mode') != MODE_WAIT_DATA:
        return

    text = (update.message.text or "").strip()
    bt_key = context.user_data.get('bc_type')
    t = get_type(bt_key)
    if not t:
        return

    # Auto-uppercase for Code 39
    if bt_key == "code39":
        text = text.upper()

    if not t["validator"](text):
        await update.message.reply_text(
            f"⚠️ Invalid format for *{t['label']}*.\n\n{t['format']}\n\nTry again or /cancel.",
            parse_mode='Markdown',
        )
        return

    chat_id = update.effective_chat.id
    status = await update.message.reply_text("⏳ Generating barcode…")

    try:
        loop = asyncio.get_event_loop()
        out_bytes = await loop.run_in_executor(
            None, generate_barcode_image, t["code"], text
        )

        out_name = f"barcode_{bt_key}.png"

        await status.delete()
        # Send as photo (preview) and document (hi-res)
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=InputFile(io.BytesIO(out_bytes), filename=out_name),
            caption=f"✅ *Barcode Ready!*\n\nType: {t['label']}\nData: `{text}`",
            parse_mode='Markdown',
        )
        await context.bot.send_document(
            chat_id=chat_id,
            document=InputFile(io.BytesIO(out_bytes), filename=out_name),
            caption="📥 Hi-res PNG (ready to print)",
            reply_markup=main_menu_markup(),
        )

    except Exception as e:
        logger.error(f"Barcode generation failed: {e}")
        try:
            await status.delete()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Failed: {e}",
            reply_markup=main_menu_markup(),
        )
    finally:
        reset_user_state(context)


# ---------- Barcode generation ----------

def generate_barcode_image(code_type: str, data: str) -> bytes:
    """Render barcode to PNG bytes using python-barcode."""
    BARCODE_CLASS = barcode.get_barcode_class(code_type)

    writer = ImageWriter()
    options = {
        "module_width": 0.35,
        "module_height": 18.0,
        "quiet_zone": 4,
        "font_size": 12,
        "text_distance": 5,
        "background": "white",
        "foreground": "black",
        "write_text": True,
    }

    bc = BARCODE_CLASS(data, writer=writer)
    buf = io.BytesIO()
    bc.write(buf, options=options)
    buf.seek(0)

    # Optionally upscale for crisp print quality
    img = Image.open(buf).convert("RGB")
    w, h = img.size
    if w < 1200:
        scale = 1200 / w
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


# ---------- Dummy web server (keeps Render Web Service alive) ----------

async def health(request):
    return web.Response(text="Bot is running")


async def run_web():
    port = int(os.environ.get("PORT", 10000))
    app = web.Application()
    app.router.add_get("/", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logger.info(f"Health server listening on port {port}")


# ---------- Runner ----------

async def run_bot():
    if not BOT_TOKEN:
        logger.critical("FATAL: BARCODE_BOT_TOKEN is missing!")
        return

    try:
        application = Application.builder().token(BOT_TOKEN).build()

        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("cancel", cancel_command))
        application.add_handler(CallbackQueryHandler(menu_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

        await run_web()

        logger.info("Bot is now polling...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)

        stop_event = asyncio.Event()
        await stop_event.wait()

    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
    finally:
        if 'application' in locals():
            await application.stop()
            await application.shutdown()


def main():
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    except Exception as e:
        logger.error(f"Main loop error: {e}")


if __name__ == '__main__':
    main()
