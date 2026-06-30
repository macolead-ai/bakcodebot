import logging
import os
import asyncio
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get('BOT_TOKEN')

# ⚠️ Must match the exact filename in your GitHub repo (root folder)
VIDEO_FILENAME = "mariah copy trade ingles _1080p.mp4"


# ---------- Localized welcome text ----------

def get_welcome_text(lang: str) -> str:
    if lang == "pt":
        return (
            "💎 Bem-vindo à estrutura oficial da Mariah Trader.\n\n"
            "Você acaba de entrar em um ecossistema completo de educação de trading construído para disciplina, estratégia e execução inteligente.\n\n"
            "Aqui dentro, você encontrará:\n\n"
            "🤖 Robô automatizado conectado à Quotex\n"
            "🔁 Estrutura inteligente de CopyTrade\n"
            "📊 Salas VIP com análises filtradas do mercado\n"
            "📱 App exclusivo com abordagem sem Martingale\n"
            "🎯 Estratégias adaptadas para os tempos gráficos de M1, M5 e M15\n\n"
            "Para ativar seu acesso completo, siga os próximos passos abaixo. 👇"
        )
    elif lang == "es":
        return (
            "💎 Bienvenido a la estructura oficial de Mariah Trader.\n\n"
            "Acabas de entrar en un ecosistema completo de educación de trading diseñado para la disciplina, la estrategia y la ejecución inteligente.\n\n"
            "Aquí dentro encontrarás:\n\n"
            "🤖 Robot automatizado conectado a Quotex\n"
            "🔁 Estructura inteligente de CopyTrade\n"
            "📊 Salas VIP con análisis de mercado filtrados\n"
            "📱 App exclusiva con enfoque sin Martingale\n"
            "🎯 Estrategias adaptadas para temporalidades de M1, M5 y M15\n\n"
            "Para activar tu acceso completo, sigue los siguientes pasos a continuación. 👇"
        )
    else:
        return (
            "💎 Welcome to the official Mariah Trader structure.\n\n"
            "You have just entered a complete trading education ecosystem built for discipline, strategy and smart execution.\n\n"
            "Inside, you will find:\n\n"
            "🤖 Automated robot connected to Quotex\n"
            "🔁 Intelligent CopyTrade structure\n"
            "📊 VIP rooms with filtered market insights\n"
            "📱 Exclusive app with no Martingale approach\n"
            "🎯 Strategies adapted for M1, M5 and M15 timeframes\n\n"
            "To activate your full access, follow the next steps below. 👇"
        )


# ---------- /start: show language buttons FIRST ----------

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logger.info(f"User {user.id} started the bot")

    lang_text = (
        "Bem vindo! 🇧🇷 É um prazer ter você aqui. Escolha o seu idioma e acesse conteúdo exclusivo agora!\n\n"
        "¡Bienvenido! 🇪🇸 Es un placer tenerle aquí. ¡Elija su idioma y acceda a contenido exclusivo ahora!\n\n"
        "Welcome! 🇺🇸 It's a pleasure to have you here. Choose your language and access exclusive content now!"
    )
    keyboard = [
        [
            InlineKeyboardButton("🇧🇷 PT", callback_data="lang_pt"),
            InlineKeyboardButton("🇪🇸 ES", callback_data="lang_es"),
            InlineKeyboardButton("🇺🇸 EN", callback_data="lang_en"),
        ]
    ]
    await update.message.reply_text(lang_text, reply_markup=InlineKeyboardMarkup(keyboard))


# ---------- Language pick: send video + welcome text ----------

async def language_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not query.data.startswith("lang_"):
        return

    lang = query.data.split("_", 1)[1]
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    logger.info(f"User {user_id} picked language: {lang}")

    # Remove the language-selection message to keep the chat clean
    try:
        await query.message.delete()
    except Exception as e:
        logger.warning(f"Could not delete language message: {e}")

    # Send the video as a streaming inline video (NOT a downloadable file)
    if os.path.exists(VIDEO_FILENAME):
        try:
            with open(VIDEO_FILENAME, 'rb') as video_file:
                await context.bot.send_video(
                    chat_id=chat_id,
                    video=video_file,
                    supports_streaming=True,   # ← makes it play inline
                )
        except Exception as e:
            logger.error(f"Error sending video: {e}")
    else:
        logger.warning(f"Video file '{VIDEO_FILENAME}' not found in repo!")

    # Then send the localized welcome text
    await context.bot.send_message(
        chat_id=chat_id,
        text=get_welcome_text(lang),
        disable_web_page_preview=True,
    )


# ---------- Health server (keeps Render alive) ----------

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
        logger.critical("BOT_TOKEN env var missing!")
        return

    application = None
    try:
        application = Application.builder().token(BOT_TOKEN).build()
        application.add_handler(CommandHandler("start", start_command))
        application.add_handler(CallbackQueryHandler(language_callback, pattern=r"^lang_"))

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
