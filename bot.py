"""
Bot de Telegram educativo de trading — 100% gratis para los usuarios.
El usuario escribe un término (ej. "que es un FVG") y recibe la explicación
+ un enlace a video de YouTube en español o inglés. También incluye:
- Modo quiz aleatorio (/quiz)
- Navegación guiada por módulos (/temas): elige un módulo, estudia tema por
  tema con una mini-pregunta de refuerzo después de cada uno (se repite
  hasta acertar), y al terminar todos los temas del módulo se lanza un
  examen final con una pregunta por cada subtema estudiado.

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

# Descripción corta de qué trae cada módulo (para el menú de /temas)
MODULOS = {
    0: "Fundamentos: qué es el trading, trading vs inversión, riesgo y beneficio.",
    1: "Mercados financieros: centralizados, OTC, cripto (CEX/DEX), sesiones de mercado.",
    2: "Tipos de activos: cripto, forex, acciones, índices, materias primas, futuros, opciones, ETFs.",
    3: "Plataformas y herramientas: brokers para Cuba y globales, análisis, backtesting.",
    4: "Gráficas: herramientas, temporalidades, tipos de gráfico, tipos de velas.",
    5: "Tipos de trader: binario, scalping, day trading, swing, position, value investing.",
    6: "Conceptos de trading: OB, FVG, sweeps, SL/TP, liquidez, BOS/CHoCH, spread, comisiones.",
    7: "Indicadores: qué son, EMA, volumen, ATR, RSI, MACD, Bollinger, VWAP.",
    8: "Estrategias: qué es una estrategia, Tortugas, SMC, ICT, Bias.",
    9: "Información para Cuba (próximamente).",
}


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
# Utilidades
# ---------------------------------------------------------------------------

def formatear_respuesta(topic: dict) -> tuple[str, list]:
    """Texto + filas de botones (videos) para un tema. No incluye botón de
    volver/menú; eso lo agrega quien llama según el contexto."""
    texto = f"📘 *{topic['titulo']}*\n\n{topic['definicion']}"

    video_es = topic.get("video_es")
    video_en = topic.get("video_en")
    if not video_es and not video_en:
        texto += "\n\n🎥 _Video en revisión — se añadirá pronto._"

    fila_videos = []
    if video_es:
        fila_videos.append(InlineKeyboardButton("🎥 Video (ES)", url=video_es))
    if video_en:
        fila_videos.append(InlineKeyboardButton("🎥 Video (EN)", url=video_en))

    filas = [fila_videos] if fila_videos else []
    return texto, filas


def generar_opciones(correcto_id: str, k: int = 3):
    """Devuelve la lista de temas-opción (incluye el correcto) ya mezclada."""
    temas = search.todos_los_temas()
    correcto = search.tema_por_id(correcto_id)
    distractores = random.sample([t for t in temas if t["id"] != correcto_id], k=k)
    opciones = distractores + [correcto]
    random.shuffle(opciones)
    return opciones


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.ensure_user(user.id, user.username)
    await con_reintentos(
        update.message.reply_text,
        "👋 ¡Hola! Soy tu bot de trading.\n\n"
        "Escríbeme cualquier término (ej. *que es un order block*, *fair value gap*, "
        "*gestión de riesgo*) y te doy la explicación + un video para reforzar.\n\n"
        "Comandos:\n"
        "/temas — estudiar por módulos, tema a tema, con quiz de refuerzo\n"
        "/quiz — pregunta aleatoria de cualquier tema\n"
        "/stats — tus estadísticas de quiz\n"
        "/ayuda — ver esta ayuda de nuevo",
        parse_mode="Markdown",
    )


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await start(update, context)


async def listar_temas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/temas: muestra los módulos como botones, con una línea de qué trae cada uno.
    Funciona tanto llamada desde el comando /temas (update.message) como desde
    un botón (update.callback_query, donde update.message no existe)."""
    chat_id = update.effective_chat.id

    lineas = ["📚 *Elige un módulo para estudiar:*\n"]
    botones = []
    for n in sorted(MODULOS):
        lineas.append(f"*Módulo {n}* — {MODULOS[n]}")
        botones.append([InlineKeyboardButton(f"Módulo {n}", callback_data=f"modulo:{n}")])

    texto = "\n\n".join(lineas)
    for i in range(0, len(texto), 3500):
        parte = texto[i:i + 3500]
        markup = InlineKeyboardMarkup(botones) if i + 3500 >= len(texto) else None
        await con_reintentos(
            context.bot.send_message, chat_id, parte, parse_mode="Markdown", reply_markup=markup
        )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.ensure_user(user.id, user.username)
    s = db.get_stats(user.id)
    total = s["correctas"] + s["incorrectas"]
    porcentaje = (s["correctas"] / total * 100) if total else 0
    await con_reintentos(
        update.message.reply_text,
        f"📊 *Tus estadísticas*\n\n"
        f"✅ Correctas: {s['correctas']}\n"
        f"❌ Incorrectas: {s['incorrectas']}\n"
        f"🎯 Aciertos: {porcentaje:.0f}%\n"
        f"🔥 Racha actual: {s['racha_actual']}\n"
        f"🏆 Mejor racha: {s['mejor_racha']}",
        parse_mode="Markdown",
    )


async def quiz_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await enviar_pregunta_suelta(update.effective_chat.id, context)


# ---------------------------------------------------------------------------
# Quiz suelto (/quiz y botón "Quiz de este tema")
# ---------------------------------------------------------------------------

async def enviar_pregunta_suelta(chat_id: int, context: ContextTypes.DEFAULT_TYPE, topic_id: str | None = None):
    temas = search.todos_los_temas()
    correcto = search.tema_por_id(topic_id) if topic_id else random.choice(temas)
    opciones = generar_opciones(correcto["id"])

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


# ---------------------------------------------------------------------------
# Navegación por módulos
# ---------------------------------------------------------------------------

async def mostrar_submenu_modulo(query, context, modulo: int):
    temas = [t for t in search.todos_los_temas() if t["modulo"] == modulo]
    botones = [[InlineKeyboardButton("📖 Estudiar todo este módulo", callback_data=f"estudiar:{modulo}")]]
    for t in temas:
        botones.append([InlineKeyboardButton(t["titulo"], callback_data=f"tema:{t['id']}:{modulo}")])
    botones.append([InlineKeyboardButton("⬅️ Volver a los módulos", callback_data="volver_modulos")])

    texto = f"*Módulo {modulo}*\n{MODULOS[modulo]}\n\nElige un tema puntual o estudia todo el módulo seguido:"
    await con_reintentos(
        query.edit_message_text, texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(botones)
    )


async def enviar_paso_leccion(chat_id: int, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Envía la definición del tema actual de la lección + su mini-quiz de refuerzo."""
    leccion = context.user_data["leccion"]
    modulo, temas_ids, indice = leccion["modulo"], leccion["temas_ids"], leccion["indice"]
    topic = search.tema_por_id(temas_ids[indice])

    texto_tema, filas_video = formatear_respuesta(topic)
    texto_tema += f"\n\n_Tema {indice + 1} de {len(temas_ids)} del módulo {modulo}_"
    if filas_video:
        await con_reintentos(
            context.bot.send_message, chat_id, texto_tema, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(filas_video),
        )
    else:
        await con_reintentos(context.bot.send_message, chat_id, texto_tema, parse_mode="Markdown")

    await enviar_pregunta_leccion(chat_id, context)


async def enviar_pregunta_leccion(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    leccion = context.user_data["leccion"]
    topic = search.tema_por_id(leccion["temas_ids"][leccion["indice"]])
    opciones = generar_opciones(topic["id"])
    botones = [
        [InlineKeyboardButton(o["titulo"], callback_data=f"lresp:{o['id']}")]
        for o in opciones
    ]
    await con_reintentos(
        context.bot.send_message,
        chat_id,
        f"🧠 *Para fijar el concepto:*\n\n{topic['definicion']}\n\n¿A qué concepto corresponde?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(botones),
    )


async def iniciar_examen_modulo(chat_id: int, context: ContextTypes.DEFAULT_TYPE, modulo: int):
    temas_modulo = [t for t in search.todos_los_temas() if t["modulo"] == modulo]
    preguntas = []
    for t in temas_modulo:
        preguntas.append({"correcto_id": t["id"], "opciones": [o["id"] for o in generar_opciones(t["id"])]})
    random.shuffle(preguntas)

    context.user_data["examen"] = {"modulo": modulo, "preguntas": preguntas, "indice": 0, "correctas": 0}
    context.user_data.pop("leccion", None)

    await con_reintentos(
        context.bot.send_message,
        chat_id,
        f"📝 *Examen final — Módulo {modulo}*\n\n{len(preguntas)} preguntas, una por cada tema que estudiaste. ¡Vamos!",
        parse_mode="Markdown",
    )
    await enviar_pregunta_examen(chat_id, context)


async def enviar_pregunta_examen(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    examen = context.user_data["examen"]
    p = examen["preguntas"][examen["indice"]]
    correcto = search.tema_por_id(p["correcto_id"])
    opciones = [search.tema_por_id(oid) for oid in p["opciones"]]

    botones = [
        [InlineKeyboardButton(o["titulo"], callback_data=f"eresp:{o['id']}")]
        for o in opciones
    ]
    await con_reintentos(
        context.bot.send_message,
        chat_id,
        f"📝 *Pregunta {examen['indice'] + 1}/{len(examen['preguntas'])}:*\n\n{correcto['definicion']}\n\n¿A qué concepto corresponde?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(botones),
    )


# ---------------------------------------------------------------------------
# Callbacks (botones)
# ---------------------------------------------------------------------------

async def manejar_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user = update.effective_user
    db.ensure_user(user.id, user.username)
    chat_id = query.message.chat_id
    data = query.data

    # --- Menú de módulos ---
    if data == "volver_modulos":
        await listar_temas(update, context)
        return

    if data.startswith("modulo:"):
        modulo = int(data.split(":", 1)[1])
        await mostrar_submenu_modulo(query, context, modulo)
        return

    if data.startswith("tema:"):
        _, topic_id, modulo = data.split(":")
        topic = search.tema_por_id(topic_id)
        db.log_consulta(user.id, topic_id)
        texto, filas = formatear_respuesta(topic)
        filas.append([InlineKeyboardButton("⬅️ Volver al módulo", callback_data=f"modulo:{modulo}")])
        await con_reintentos(
            query.edit_message_text, texto, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(filas)
        )
        return

    # --- Lección guiada por módulo ---
    if data.startswith("estudiar:"):
        modulo = int(data.split(":", 1)[1])
        temas_ids = [t["id"] for t in search.todos_los_temas() if t["modulo"] == modulo]
        random.shuffle(temas_ids)
        context.user_data["leccion"] = {"modulo": modulo, "temas_ids": temas_ids, "indice": 0}
        await con_reintentos(
            query.edit_message_text, f"📖 Empezando el Módulo {modulo} — {len(temas_ids)} temas.", parse_mode="Markdown"
        )
        await enviar_paso_leccion(chat_id, context, user.id)
        return

    if data.startswith("lresp:"):
        elegido_id = data.split(":", 1)[1]
        leccion = context.user_data.get("leccion")
        if not leccion:
            return  # sesión vieja/expirada, se ignora
        topic_actual = search.tema_por_id(leccion["temas_ids"][leccion["indice"]])
        acierto = elegido_id == topic_actual["id"]
        db.registrar_respuesta(user.id, acierto)

        if acierto:
            leccion["indice"] += 1
            if leccion["indice"] < len(leccion["temas_ids"]):
                await con_reintentos(
                    query.edit_message_text, "✅ ¡Correcto! Vamos con el siguiente tema...", parse_mode="Markdown"
                )
                await enviar_paso_leccion(chat_id, context, user.id)
            else:
                await con_reintentos(
                    query.edit_message_text,
                    "✅ ¡Correcto! Terminaste todos los temas de este módulo.",
                    parse_mode="Markdown",
                )
                await iniciar_examen_modulo(chat_id, context, leccion["modulo"])
        else:
            await con_reintentos(
                query.edit_message_text,
                f"❌ No es esa. La respuesta correcta era *{topic_actual['titulo']}*.\nInténtalo de nuevo:",
                parse_mode="Markdown",
            )
            await enviar_pregunta_leccion(chat_id, context)
        return

    # --- Examen final del módulo ---
    if data.startswith("eresp:"):
        elegido_id = data.split(":", 1)[1]
        examen = context.user_data.get("examen")
        if not examen:
            return
        p = examen["preguntas"][examen["indice"]]
        acierto = elegido_id == p["correcto_id"]
        db.registrar_respuesta(user.id, acierto)
        if acierto:
            examen["correctas"] += 1

        correcto_topic = search.tema_por_id(p["correcto_id"])
        prefijo = "✅ ¡Correcto!" if acierto else f"❌ No era esa (era *{correcto_topic['titulo']}*)."
        await con_reintentos(query.edit_message_text, prefijo, parse_mode="Markdown")

        examen["indice"] += 1
        if examen["indice"] < len(examen["preguntas"]):
            await enviar_pregunta_examen(chat_id, context)
        else:
            total = len(examen["preguntas"])
            correctas = examen["correctas"]
            porcentaje = correctas / total * 100
            modulo_terminado = examen["modulo"]
            botones = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🔁 Repetir examen", callback_data=f"repetir_examen:{modulo_terminado}")],
                    [InlineKeyboardButton("📖 Repetir estudio del módulo", callback_data=f"estudiar:{modulo_terminado}")],
                    [InlineKeyboardButton("⬅️ Volver a los módulos", callback_data="volver_modulos")],
                ]
            )
            await con_reintentos(
                context.bot.send_message,
                chat_id,
                f"🏁 *Examen del Módulo {modulo_terminado} terminado*\n\n"
                f"Resultado: {correctas}/{total} correctas ({porcentaje:.0f}%)",
                parse_mode="Markdown",
                reply_markup=botones,
            )
            context.user_data.pop("examen", None)
        return

    if data.startswith("repetir_examen:"):
        modulo = int(data.split(":", 1)[1])
        await iniciar_examen_modulo(chat_id, context, modulo)
        return

    # --- Quiz suelto (/quiz) ---
    if data.startswith("quiz:"):
        topic_id = data.split(":", 1)[1]
        await enviar_pregunta_suelta(chat_id, context, topic_id=topic_id)
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
        await enviar_pregunta_suelta(chat_id, context)
        return

    if data.startswith("video:"):
        topic_id = data.split(":", 1)[1]
        topic = search.tema_por_id(topic_id)
        texto, filas = formatear_respuesta(topic)
        await con_reintentos(
            context.bot.send_message, chat_id, texto, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(filas) if filas else None,
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
            await con_reintentos(
                update.message.reply_text,
                "🤔 No estoy seguro de haber entendido. ¿Quizás buscas alguno de estos?",
                reply_markup=botones,
            )
        else:
            await con_reintentos(
                update.message.reply_text,
                "🤔 No encontré ese tema todavía. Prueba con /temas para ver la lista completa.",
            )
        return

    db.log_consulta(user.id, topic["id"])
    texto, filas = formatear_respuesta(topic)
    await con_reintentos(
        update.message.reply_text, texto, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(filas) if filas else None,
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
