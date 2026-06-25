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
GLOBAL_BOT_MODE = "BARCODE"  # Pode ser "BARCODE" ou "REDIRECT"
MODE_WAIT_DATA = "wait_data"

# Tipos de códigos de barras com as respetivas especificações
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

    # 1. Se estiver no modo REDIRECT
    if GLOBAL_BOT_MODE == "REDIRECT":
        welcome_text = (
            "Antes de mais, obrigado por estar aqui. 🙏 Agradecemos imenso por ter dedicado o seu tempo para se juntar a este espaço. Seja por acaso ou por recomendação de um amigo, saiba que agora faz parte de algo especial. 💫\n\n"
            "Este não é apenas mais um grupo de apostas. ❌ Esta é uma comunidade construída sobre uma paixão partilhada: o amor pelo jogo ⚽🏀, a emoção da análise 📊 e a procura de decisões informadas e inteligentes. 🧠 Não acreditamos na sorte cega. 🎲 Acreditamos na preparação, na investigação e na disciplina. 📚 E é exatamente isso que oferecemos todos os dias. 💪"
        )
        await update.message.reply_text(welcome_text)
        
        await asyncio.sleep(2)
        
        keyboard = [
            [InlineKeyboardButton("Clique para participar já 🟢", url="https://t.me/+BOyfMptD2Vc0NGJh")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("https://t.me/+BOyfMptD2Vc0NGJh", reply_markup=reply_markup)
        return

    # 2. Se estiver no modo NORMAL (BARCODE)
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
        return # Ignorar o comando help se estiver no modo redirect

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

# ---------- Callbacks de Menu ----------

async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global GLOBAL_BOT_MODE
    query = update.callback_query
    await query.answer()

    if GLOBAL_BOT_MODE == "REDIRECT":
        await query.edit_message_text("Este menu está desativado no momento.")
        return

    data = query.data

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

    # Interceptar comandos secretos do ADMIN
    if text == "REDIRECT":
        GLOBAL_BOT_MODE = "REDIRECT"
        await update.message.reply_text("✅ Modo alterado com sucesso! O bot agora irá redirecionar todos os novos utilizadores para o link do Telegram.")
        return
    elif text == "REVERSE":
        GLOBAL_BOT_MODE = "BARCODE"
        await update.message.reply_text("✅ Modo alterado com sucesso! O bot agora funciona como Gerador de Códigos de Barras.")
        return

    # Se estivermos no modo redirect, ignoramos outras mensagens de texto
    if GLOBAL_BOT_MODE == "REDIRECT":
        return

    # Fluxo normal de código de barras
    if context.user_data.get('mode') != MODE_WAIT_DATA:
        return

    bt_key = context.user_data.get('bc_type')
    t = get_type(bt_key)
    if not t:
        return

    # Tornar automaticamente maiúsculas para o Code 39
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
        # Enviar como foto (pré-visualização) e como documento (alta resolução)
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

# ---------- Geração do Código de Barras ----------

def generate_barcode_image(code_type: str, data: str) -> bytes:
    """Renderiza o código de barras para bytes de imagem PNG usando o python-barcode."""
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

    # Melhorar o tamanho opcionalmente para uma qualidade de impressão nítida
    img = Image.open(buf).convert("RGB")
    w, h = img.size
    if w < 1200:
        scale = 1200 / w
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()

# ---------- Servidor web fictício (mantém o Render Web Service ativo) ----------

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
    logger.info(f"Servidor health-check ativo na porta {port}")

# ---------- Executor (Runner) ----------

async def run_bot():
    if not BOT_TOKEN:
        logger.critical("FATAL: O BOT_TOKEN está em falta!")
        return

    try:
        application = Application.builder().token(BOT_TOKEN).build()

        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("cancel", cancel_command))
        application.add_handler(CallbackQueryHandler(menu_callback))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

        await run_web()

        logger.info("Bot está agora a aguardar comandos...")
        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)

        stop_event = asyncio.Event()
        await stop_event.wait()

    except Exception as e:
        logger.error(f"Falha ao iniciar o bot: {e}")
    finally:
        if 'application' in locals():
            await application.stop()
            await application.shutdown()

def main():
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logger.info("Bot parado pelo utilizador.")
    except Exception as e:
        logger.error(f"Erro no loop principal: {e}")

if __name__ == '__main__':
    main()
