"""
Bot de Telegram educativo de trading — 100% gratis para los usuarios.
El usuario escribe un término (ej. "que es un FVG") y recibe la explicación
+ un enlace a video de YouTube en español o inglés. También incluye modo quiz.

Requiere una variable de entorno TELEGRAM_BOT_TOKEN (token de @BotFather).
"""
import logging
import os
import random
import asyncio

from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import NetworkError, TimedOut
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

import db
import search

load_dotenv()  # lee el archivo .env si existe (no falla si no existe)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")


# ---------------------------------------------------------------------------
# Utilidades
# ---------------------------------------------------------------------------

def formatear_respuesta(topic: dict, idioma_pref: str) -> tuple[str, InlineKeyboardMarkup]:
    texto = f"📘 *{topic['titulo']}*\n\n{topic['definicion']}"

    video_es = topic.get("video_es")
    video_en = topic.get("video_en")
    if not video_es and not video_en:
        texto += "\n\n🎥 _Video en revisión — se añadirá pronto._"

    botones = []
    fila_videos = []
    if video_es:
        fila_videos.append(InlineKeyboardButton("🎥 Video (ES)", url=video_es))
    if video_en:
        fila_videos.append(InlineKeyboardButton("🎥 Video (EN)", url=video_en))
    if fila_videos:
        botones.append(fila_videos)

    botones.append(
        [InlineKeyboardButton("🧠 Quiz de este tema", callback_data=f"quiz:{topic['id']}")]
    )
    return texto, InlineKeyboardMarkup(botones)


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.ensure_user(user.id, user.username)
    await update.message.reply_text(
        "👋 ¡Hola! Soy tu bot de trading.\n\n"
        "Escríbeme cualquier término (ej. *que es un order block*, *fair value gap*, "
        "*gestión de riesgo*) y te doy la explicación + un video para reforzar.\n\n"
        "Comandos:\n"
        "/quiz — pon a prueba lo que sabes\n"
        "/temas — ver todos los temas disponibles\n"
        "/stats — tus estadísticas de quiz\n"
        "/ayuda — ver esta ayuda de nuevo",
        parse_mode="Markdown",
    )


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def listar_temas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    temas = search.todos_los_temas()
    modulos = {}
    for t in temas:
        modulos.setdefault(t["modulo"], []).append(t["titulo"])

    lineas = ["📚 *Temas disponibles:*\n"]
    for modulo in sorted(modulos):
        lineas.append(f"*Módulo {modulo}*")
        lineas.extend(f"• {titulo}" for titulo in modulos[modulo])
        lineas.append("")
    texto = "\n".join(lineas)

    # Telegram limita mensajes a 4096 caracteres; se corta en varios si hace falta
    for i in range(0, len(texto), 4000):
        await update.message.reply_text(texto[i:i + 4000], parse_mode="Markdown")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.ensure_user(user.id, user.username)
    s = db.get_stats(user.id)
    total = s["correctas"] + s["incorrectas"]
    porcentaje = (s["correctas"] / total * 100) if total else 0
    await update.message.reply_text(
        f"📊 *Tus estadísticas*\n\n"
        f"✅ Correctas: {s['correctas']}\n"
        f"❌ Incorrectas: {s['incorrectas']}\n"
        f"🎯 Aciertos: {porcentaje:.0f}%\n"
        f"🔥 Racha actual: {s['racha_actual']}\n"
        f"🏆 Mejor racha: {s['mejor_racha']}",
        parse_mode="Markdown",
    )


async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await enviar_pregunta(update.effective_chat.id, context)


# ---------------------------------------------------------------------------
# Reintentos ante fallos de red (conexiones inestables hacia Telegram)
# ---------------------------------------------------------------------------

async def con_reintentos(coro_func, *args, intentos=4, espera=2, **kwargs):
    """Ejecuta una llamada a la API de Telegram reintentando si hay timeout
    o error de red, con espera creciente entre intentos."""
    ultimo_error = None
    for intento in range(1, intentos + 1):
        try:
            return await coro_func(*args, **kwargs)
        except (TimedOut, NetworkError) as e:
            ultimo_error = e
            logger.warning(f"Fallo de red (intento {intento}/{intentos}): {e}")
            if intento < intentos:
                await asyncio.sleep(espera * intento)
    raise ultimo_error


# ---------------------------------------------------------------------------
# Lógica de quiz
# ---------------------------------------------------------------------------

async def enviar_pregunta(chat_id: int, context: ContextTypes.DEFAULT_TYPE, topic_id: str | None = None):
    temas = search.todos_los_temas()
    correcto = search.tema_por_id(topic_id) if topic_id else random.choice(temas)
    distractores = random.sample(
        [t for t in temas if t["id"] != correcto["id"]], k=3
    )
    opciones = distractores + [correcto]
    random.shuffle(opciones)

    botones = [
        [InlineKeyboardButton(o["titulo"], callback_data=f"resp:{correcto['id']}:{o['id']}")]
        for o in opciones
    ]

    await con_reintentos(
        context.bot.send_message,
        chat_id,
        f"🧠 *Quiz:*\n\n{correcto['definicion']}\n\n¿A qué concepto corresponde?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(botones),
    )


async def manejar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    db.ensure_user(user.id, user.username)

    data = query.data

    if data.startswith("quiz:"):
        topic_id = data.split(":", 1)[1]
        await enviar_pregunta(query.message.chat_id, context, topic_id=topic_id)
        return

    if data.startswith("resp:"):
        _, correcto_id, elegido_id = data.split(":")
        acierto = correcto_id == elegido_id
        db.registrar_respuesta(user.id, acierto)
        topic = search.tema_por_id(correcto_id)
        if acierto:
            texto = f"✅ ¡Correcto! *{topic['titulo']}*\n\n{topic['definicion']}"
        else:
            texto = (
                f"❌ No era esa.\nLa respuesta correcta era *{topic['titulo']}*.\n\n"
                f"{topic['definicion']}"
            )
        botones = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("➡️ Otra pregunta", callback_data="quiz_nueva")],
                [InlineKeyboardButton("🎥 Ver video de este tema", callback_data=f"video:{correcto_id}")],
            ]
        )
        await con_reintentos(
            query.edit_message_text, texto, parse_mode="Markdown", reply_markup=botones
        )
        return

    if data == "quiz_nueva":
        await enviar_pregunta(query.message.chat_id, context)
        return

    if data.startswith("video:"):
        topic_id = data.split(":", 1)[1]
        topic = search.tema_por_id(topic_id)
        idioma_pref = db.get_idioma_video(user.id)
        texto, teclado = formatear_respuesta(topic, idioma_pref)
        await context.bot.send_message(
            query.message.chat_id, texto, parse_mode="Markdown", reply_markup=teclado
        )
        return


# ---------------------------------------------------------------------------
# Búsqueda por texto libre
# ---------------------------------------------------------------------------

async def responder_pregunta(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.ensure_user(user.id, user.username)

    consulta = update.message.text
    topic, score = search.buscar_tema(consulta)

    if topic is None:
        sugeridos = search.sugerencias(consulta)
        if sugeridos:
            botones = InlineKeyboardMarkup(
                [[InlineKeyboardButton(t["titulo"], callback_data=f"video:{t['id']}")] for t in sugeridos]
            )
            await update.message.reply_text(
                "🤔 No estoy seguro de haber entendido. ¿Quizás buscas alguno de estos?",
                reply_markup=botones,
            )
        else:
            await update.message.reply_text(
                "🤔 No encontré ese tema todavía. Prueba con /temas para ver la lista completa."
            )
        return

    db.log_consulta(user.id, topic["id"])
    idioma_pref = db.get_idioma_video(user.id)
    texto, teclado = formatear_respuesta(topic, idioma_pref)
    await con_reintentos(
        update.message.reply_text, texto, parse_mode="Markdown", reply_markup=teclado
    )


# ---------------------------------------------------------------------------
# Arranque
# ---------------------------------------------------------------------------

def main():
    if not TOKEN:
        raise SystemExit(
            "Falta la variable de entorno TELEGRAM_BOT_TOKEN. "
            "Consigue un token con @BotFather en Telegram y expórtala antes de correr el bot."
        )

    db.init_db()

    request = HTTPXRequest(
        connect_timeout=30.0,
        read_timeout=30.0,
        write_timeout=30.0,
        pool_timeout=30.0,
    )
    app = Application.builder().token(TOKEN).request(request).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CommandHandler("help", ayuda))
    app.add_handler(CommandHandler("temas", listar_temas))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("quiz", quiz_cmd))
    app.add_handler(CallbackQueryHandler(manejar_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder_pregunta))

    # Render define esta variable automáticamente en sus Web Services.
    # Si existe, corremos en modo webhook (producción). Si no, modo polling (local).
    render_url = os.environ.get("RENDER_EXTERNAL_URL")

    if render_url:
        port = int(os.environ.get("PORT", 10000))
        webhook_path = TOKEN  # usamos el token como ruta secreta
        logger.info(f"Bot iniciado en modo webhook en el puerto {port}...")
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path=webhook_path,
            webhook_url=f"{render_url}/{webhook_path}",
        )
    else:
        logger.info("Bot iniciado en modo polling (local). Esperando mensajes...")
        app.run_polling()


if __name__ == "__main__":
    main()
