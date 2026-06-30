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

# Ativar logs
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')

# Modos globais do Bot
GLOBAL_BOT_MODE = "BARCODE"  # "BARCODE" ou "REDIRECT"
MODE_WAIT_DATA = "wait_data"

# ⚠️ EDIT THIS: must match the exact filename of the video you uploaded to your GitHub repo root.
VIDEO_FILENAME = "intro.mp4"

# ---------- Welcome text (Mariah Trader) in 3 languages ----------
# NOTE: No channel link — SendPulse will add it via the funnel.

def get_welcome_text(lang: str) -> str:
    if lang == "pt":
        return (
            "💎 Bem-vindo à estrutura oficial da Mariah Trader.\n\n"
            "Você acaba de entrar em um ecossistema completo de educação de trading "
            "construído para disciplina, estratégia e execução inteligente.\n\n"
            "Aqui dentro, você encontrará:\n\n"
            "🤖 Robô automatizado conectado à Quotex\n"
            "🔁 Estrutura inteligente de CopyTrade\n"
            "📊 Salas VIP com análises filtradas do mercado\n"
            "📱 App exclusivo com abordagem sem Martingale\n"
            "🎯 Estratégias adaptadas para os tempos gráficos de M1, M5 e M15\n\n"
            "Para ativar seu acesso completo, siga os próximos passos abaixo. 👇"
        )
    if lang == "es":
        return (
            "💎 Bienvenido a la estructura oficial de Mariah Trader.\n\n"
            "Acabas de entrar en un ecosistema completo de educación de trading "
            "diseñado para la disciplina, la estrategia y la ejecución inteligente.\n\n"
            "Aquí dentro encontrarás:\n\n"
            "🤖 Robot automatizado conectado a Quotex\n"
            "🔁 Estructura inteligente de CopyTrade\n"
            "📊 Salas VIP con análisis de mercado filtrados\n"
            "📱 App exclusiva con enfoque sin Martingale\n"
            "🎯 Estrategias adaptadas para temporalidades de M1, M5 y M15\n\n"
            "Para activar tu acceso completo, sigue los siguientes pasos a continuación. 👇"
        )
    # English default
    return (
        "💎 Welcome to the official Mariah Trader structure.\n\n"
        "You have just entered a complete trading education ecosystem "
        "built for discipline, strategy and smart execution.\n\n"
        "Inside, you will find:\n\n"
        "🤖 Automated robot connected to Quotex\n"
        "🔁 Intelligent CopyTrade structure\n"
        "📊 VIP rooms with filtered market insights\n"
        "📱 Exclusive app with no Martingale approach\n"
        "🎯 Strategies adapted for M1, M5 and M15 timeframes\n\n"
        "To activate your full access, follow the next steps below. 👇"
    )


# ---------- Barcode types (unchanged) ----------

BARCODE_TYPES = [
    {
        "key": "ean13",
        "label": "🏷 EAN-13 (produtos de retalho)",
        "code": "ean13",
        "format": "Exatamente *12 dígitos* (dígito de controlo automático).\nExemplo: `978020137962`",
        "validator": lambda s: s.isdigit() and len(s) == 12,
    },
    {
        "key": "ean8",
        "label": "🏷 EAN-8 (retalho curto)",
        "code": "ean8",
        "format": "Exatamente *7 dígitos* (dígito de controlo automático).\nExemplo: `9638507`",
        "validator": lambda s: s.isdigit() and len(s) == 7,
    },
    {
        "key": "upca",
        "label": "🛒 UPC-A (retalho EUA/Canadá)",
        "code": "upca",
        "format": "Exatamente *11 dígitos* (dígito de controlo automático).\nExemplo: `03600029145`",
        "validator": lambda s: s.isdigit() and len(s) == 11,
    },
    {
        "key": "code128",
        "label": "🔠 Code 128 (qualquer texto)",
        "code": "code128",
        "format": "Qualquer texto ASCII (letras, números, símbolos).\nExemplo: `OLA-2025`",
        "validator": lambda s: 1 <= len(s) <= 80,
    },
    {
        "key": "code39",
        "label": "🔡 Code 39 (alfanumérico)",
        "code": "code39",
        "format": "Letras MAIÚSCULAS, números, e `-. $/+%`.\nExemplo: `PRODUTO-001`",
        "validator": lambda s: all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-. $/+%" for c in s.upper()) and len(s) <= 50,
    },
    {
        "key": "isbn13",
        "label": "📚 ISBN-13 (livros)",
        "code": "isbn13",
        "format": "Exatamente *12 dígitos* (dígito de controlo automático).\nExemplo: `978014028329`",
        "validator": lambda s: s.isdigit() and len(s) == 12,
    },
    {
        "key": "itf",
        "label": "📦 ITF (Intercalado 2 de 5)",
        "code": "itf",
        "format": "Número PAR de dígitos.\nExemplo: `1234567890`",
        "validator": lambda s: s.isdigit() and len(s) >= 4 and len(s) % 2 == 0,
    },
]

# ---------- Ajudantes ----------

def main_menu_markup() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("⚡ Criar Código de Barras", callback_data="menu_create")],
        [InlineKeyboardButton("ℹ️ Ajuda", callback_data="menu_help")],
    ]
    return InlineKeyboardMarkup(keyboard)

def types_markup() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(t["label"], callback_data=f"bt_{t['key']}")] for t in BARCODE_TYPES]
    rows.append([InlineKeyboardButton("🏠 Menu Principal", callback_data="menu_home")])
    return InlineKeyboardMarkup(rows)

def language_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🇧🇷 PT", callback_data="lang_pt"),
        InlineKeyboardButton("🇪🇸 ES", callback_data="lang_es"),
        InlineKeyboardButton("🇺🇸 EN", callback_data="lang_en"),
    ]])

def reset_user_state(context: ContextTypes.DEFAULT_TYPE) -> None:
    for key in ('mode', 'bc_type'):
        context.user_data.pop(key, None)

def get_type(key: str):
    for t in BARCODE_TYPES:
        if t["key"] == key:
            return t
    return None

# ---------- Comandos ----------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GLOBAL_BOT_MODE
    user = update.effective_user
    logger.info(f"User {user.id} started the bot in mode: {GLOBAL_BOT_MODE}")
    reset_user_state(context)

    # ===== REDIRECT MODE: language selector first =====
    if GLOBAL_BOT_MODE == "REDIRECT":
        lang_text = (
            "Bem vindo! 🇧🇷 É um prazer ter você aqui. Escolha o seu idioma e acesse conteúdo exclusivo agora!\n\n"
            "¡Bienvenido! 🇪🇸 Es un placer tenerle aquí. ¡Elija su idioma y acceda a contenido exclusivo ahora!\n\n"
            "Welcome! 🇺🇸 It's a pleasure to have you here. Choose your language and access exclusive content now!"
        )
        await update.message.reply_text(lang_text, reply_markup=language_markup())
        return

    # ===== BARCODE MODE: original generator menu =====
    welcome = (
        "👋 *Bem-vindo ao Gerador de Códigos de Barras!*\n\n"
        "Eu crio códigos de barras profissionais em segundos 📊\n\n"
        "✨ *7 formatos suportados:*\n"
        "• 🏷 EAN-13 / EAN-8\n"
        "• 🛒 UPC-A\n"
        "• 🔠 Code 128 / Code 39\n"
        "• 📚 ISBN-13\n"
        "• 📦 ITF\n\n"
        "Resultado: imagem PNG de alta resolução pronta a imprimir!\n\n"
        "Toque abaixo para começar:"
    )
    await update.message.reply_text(welcome, reply_markup=main_menu_markup(), parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GLOBAL_BOT_MODE
    if GLOBAL_BOT_MODE == "REDIRECT":
        return

    text = (
        "ℹ️ *Como usar*\n\n"
        "1. Toque em ⚡ *Criar Código de Barras*\n"
        "2. Escolha o formato desejado\n"
        "3. Envie os dados (números ou texto)\n"
        "4. Receba o seu código de barras!\n\n"
        "💡 *Guia rápido:*\n"
        "• `EAN-13` → produtos de retalho a nível mundial\n"
        "• `UPC-A` → produtos de retalho EUA/Canadá\n"
        "• `Code 128` → qualquer texto, muito comum em logística\n"
        "• `Code 39` → uso industrial, letras maiúsculas\n"
        "• `ISBN` → livros\n\n"
        "Use /cancel a qualquer momento para reiniciar."
    )
    if update.message:
        await update.message.reply_text(text, parse_mode='Markdown', reply_markup=main_menu_markup())
    else:
        await update.callback_query.edit_message_text(
            text, parse_mode='Markdown', reply_markup=main_menu_markup()
        )

async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GLOBAL_BOT_MODE
    if GLOBAL_BOT_MODE == "REDIRECT":
        return
    reset_user_state(context)
    await update.message.reply_text(
        "❌ Ação cancelada. Use /start para recomeçar.",
        reply_markup=main_menu_markup(),
    )

# ---------- Callbacks ----------

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GLOBAL_BOT_MODE
    query = update.callback_query
    await query.answer()
    data = query.data

    # ===== Language selection works even in REDIRECT mode =====
    if data.startswith("lang_"):
        lang = data.split("_", 1)[1]
        chat_id = query.message.chat_id
        logger.info(f"User {query.from_user.id} picked language: {lang}")

        # Remove the language selection message
        try:
            await query.message.delete()
        except Exception as e:
            logger.warning(f"Could not delete language message: {e}")

        # 1. Send the video (inline, streaming)
        if os.path.exists(VIDEO_FILENAME):
            try:
                with open(VIDEO_FILENAME, 'rb') as video_file:
                    await context.bot.send_video(
                        chat_id=chat_id,
                        video=video_file,
                        supports_streaming=True,
                    )
            except Exception as e:
                logger.error(f"Error sending video: {e}")
        else:
            logger.warning(f"Video file '{VIDEO_FILENAME}' not found at repo root")

        # 2. Send the localized welcome text (no link — SendPulse handles that)
        await context.bot.send_message(
            chat_id=chat_id,
            text=get_welcome_text(lang),
            disable_web_page_preview=True,
        )
        return

    # ===== Block other menus in REDIRECT mode =====
    if GLOBAL_BOT_MODE == "REDIRECT":
        await query.edit_message_text("Este menu está desativado no momento.")
        return

    # ===== Barcode menus (unchanged) =====
    if data == "menu_home":
        reset_user_state(context)
        await query.edit_message_text(
            "🏠 *Menu Principal*\nEscolha uma opção abaixo:",
            reply_markup=main_menu_markup(),
            parse_mode='Markdown',
        )
    elif data == "menu_help":
        await help_command(update, context)
    elif data == "menu_create":
        await query.edit_message_text(
            "⚡ *Criar Código de Barras*\n\nEscolha um formato:",
            reply_markup=types_markup(),
            parse_mode='Markdown',
        )
    elif data.startswith("bt_"):
        bt_key = data.split("_", 1)[1]
        t = get_type(bt_key)
        if not t:
            await query.edit_message_text("⚠️ Formato desconhecido.", reply_markup=main_menu_markup())
            return
        context.user_data['bc_type'] = bt_key
        context.user_data['mode'] = MODE_WAIT_DATA
        await query.edit_message_text(
            f"📥 *{t['label']}*\n\n"
            f"Envie os dados que pretende codificar:\n\n{t['format']}\n\n"
            "_Use /cancel para abortar._",
            parse_mode='Markdown',
        )

# ---------- Tratamento de Texto ----------

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GLOBAL_BOT_MODE
    text = (update.message.text or "").strip()

    # Admin secret commands
    if text == "REDIRECT":
        GLOBAL_BOT_MODE = "REDIRECT"
        await update.message.reply_text("✅ Modo alterado! O bot agora apresenta o seletor de idioma do funil Mariah Trader.")
        return
    if text == "REVERSE":
        GLOBAL_BOT_MODE = "BARCODE"
        await update.message.reply_text("✅ Modo alterado! O bot agora funciona como Gerador de Códigos de Barras.")
        return

    # REDIRECT mode: ignore all other text
    if GLOBAL_BOT_MODE == "REDIRECT":
        return

    # Barcode flow
    if context.user_data.get('mode') != MODE_WAIT_DATA:
        return

    bt_key = context.user_data.get('bc_type')
    t = get_type(bt_key)
    if not t:
        return

    if bt_key == "code39":
        text = text.upper()

    if not t["validator"](text):
        await update.message.reply_text(
            f"⚠️ Formato inválido para *{t['label']}*.\n\n{t['format']}\n\nTente novamente ou use /cancel.",
            parse_mode='Markdown',
        )
        return

    chat_id = update.effective_chat.id
    status = await update.message.reply_text("⏳ A gerar o código de barras…")

    try:
        loop = asyncio.get_event_loop()
        out_bytes = await loop.run_in_executor(
            None, generate_barcode_image, t["code"], text
        )
        out_name = f"codigo_{bt_key}.png"

        await status.delete()
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=InputFile(io.BytesIO(out_bytes), filename=out_name),
            caption=f"✅ *Código de Barras Pronto!*\n\nTipo: {t['label']}\nDados: `{text}`",
            parse_mode='Markdown',
        )
        await context.bot.send_document(
            chat_id=chat_id,
            document=InputFile(io.BytesIO(out_bytes), filename=out_name),
            caption="📥 PNG em alta resolução (pronto a imprimir)",
            reply_markup=main_menu_markup(),
        )
    except Exception as e:
        logger.error(f"Falha na geração do código de barras: {e}")
        try:
            await status.delete()
        except Exception:
            pass
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"❌ Ocorreu um erro: {e}",
            reply_markup=main_menu_markup(),
        )
    finally:
        reset_user_state(context)

# ---------- Geração de Código de Barras ----------

def generate_barcode_image(code_type: str, data: str) -> bytes:
    BARCODE_CLASS = barcode.get_barcode_class(code_type)
    writer = ImageWriter()
    options = {
        "module_width": 0.35, "module_height": 18.0, "quiet_zone": 4,
        "font_size": 12, "text_distance": 5,
        "background": "white", "foreground": "black", "write_text": True,
    }
    bc = BARCODE_CLASS(data, writer=writer)
    buf = io.BytesIO()
    bc.write(buf, options=options)
    buf.seek(0)

    img = Image.open(buf).convert("RGB")
    w, h = img.size
    if w < 1200:
        scale = 1200 / w
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()

# ---------- Health server ----------

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
    logger.info(f"Health server on port {port}")

# ---------- Runner ----------

async def run_bot():
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN missing!")
        return

    application = None
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("cancel", cancel_command))
        application.add_handler(CallbackQueryHandler(menu_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

        await run_web()

        logger.info("Bot está a correr...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)

        await asyncio.Event().wait()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
    finally:
        if application is not None:
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
