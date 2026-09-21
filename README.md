# TradeSchoolBot 🧠

Bot de Telegram educativo de trading — 100% gratis para los usuarios. El
usuario escribe un término (ej. "que es un order block") y recibe la
explicación + un enlace a video de YouTube en español o inglés para
reforzar. También incluye modo quiz con estadísticas de progreso.

Bot en Telegram: [@TradeSchoolHQBot](https://t.me/TradeSchoolHQBot)

---

## 1. Estructura del proyecto

```
TradeSchoolBot/
├── content.json     ← Base de conocimiento (64 temas, módulos 0-11)
├── search.py        ← Búsqueda difusa de temas (fuzzy matching, sin API)
├── db.py            ← Progreso de usuarios (SQLite)
├── bot.py           ← Bot de Telegram (comandos + quiz)
├── requirements.txt
├── .env.example     ← Plantilla de variables de entorno
└── .gitignore
```

## 2. Instalación y ejecución local

### 2.1 Crear el entorno virtual

```bash
python3 -m venv venv
```

Esto crea una carpeta `venv/` con un Python aislado solo para este
proyecto, evitando el error `externally-managed-environment` de Ubuntu/Debian.

### 2.2 Activarlo

```bash
source venv/bin/activate
```

Sabrás que funcionó porque el inicio de tu terminal cambia a algo como
`(venv) usuario@equipo:...`. Hay que activar el entorno cada vez que abras
una terminal nueva para trabajar en el proyecto.

### 2.3 Instalar las dependencias

```bash
pip install -r requirements.txt
```

### 2.4 Configurar el token del bot

Crea un archivo `.env` en la raíz del proyecto (puedes copiar
`.env.example`) con esta línea:

```
TELEGRAM_BOT_TOKEN=tu_token_de_botfather
```

El token se obtiene hablando con [@BotFather](https://t.me/BotFather) en
Telegram (`/newbot`). **Nunca subas este archivo a GitHub** — ya está
incluido en `.gitignore`.

### 2.5 Correr el bot

```bash
python bot.py
```

Si todo va bien, verás en la terminal:

```
Bot iniciado. Esperando mensajes...
```

Abre [@TradeSchoolHQBot](https://t.me/TradeSchoolHQBot) en Telegram y
mándale `/start`.

## 3. Comandos disponibles

| Comando | Qué hace |
|---|---|
| `/start` | Bienvenida y explicación |
| `/ayuda` | Vuelve a mostrar la ayuda |
| `/temas` | Lista todos los temas disponibles por módulo |
| `/quiz` | Lanza una pregunta aleatoria |
| `/stats` | Aciertos, fallos y racha del usuario |
| *(texto libre)* | Busca el término más parecido y responde con su explicación |

## 4. Añadir o curar videos de YouTube

Cada tema en `content.json` tiene los campos `video_es` y `video_en`.
Mientras estén en `null`, el bot avisa "video en revisión" en vez de
romperse. Para activarlos, solo pega el link:

```json
{
  "id": "fvg",
  "titulo": "Fair Value Gap (FVG)",
  "video_es": "https://youtube.com/watch?v=XXXXX",
  "video_en": "https://youtube.com/watch?v=YYYYY"
}
```

No hace falta tocar el código — se recarga solo al reiniciar el bot.
Prioriza el Módulo 11 (SMC avanzado).

## 5. Ampliar la base de contenido

Para agregar un tema nuevo, añade un objeto más en `content.json` con el
mismo formato (`id`, `modulo`, `titulo`, `keywords`, `definicion`,
`video_es`, `video_en`). Cuantas más `keywords` (sinónimos, errores
comunes, abreviaturas) le des, mejor va a entender el buscador las
preguntas de los usuarios.

## 6. Solución de problemas

**`ModuleNotFoundError: No module named 'db'` (o `search`)**
Falta ese archivo en la carpeta del proyecto — verifica con `ls` que estén
los 5 archivos: `bot.py`, `content.json`, `db.py`, `search.py`,
`requirements.txt`.

**`externally-managed-environment` al hacer `pip install`**
No estás usando el entorno virtual. Sigue los pasos 2.1 y 2.2 antes de
instalar.

**`telegram.error.TimedOut` / `httpx.ConnectTimeout`**
Corte de red puntual hacia los servidores de Telegram. El bot ya reintenta
automáticamente hasta 4 veces con tiempos de espera más largos; si persiste
seguido, puede requerir una conexión más estable o un proxy hacia Telegram.

## 7. Despliegue 24/7 (próximo paso)

Por ahora el bot corre en local (solo funciona mientras `python bot.py`
esté activo en tu computadora). El siguiente paso es desplegarlo en
**Render** en modo webhook para que quede disponible todo el tiempo sin
depender de tu equipo — se documentará aquí una vez esté configurado.
