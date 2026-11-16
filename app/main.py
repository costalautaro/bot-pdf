"""Punto de entrada de la aplicación.

Vercel detecta automáticamente la instancia `app` en `app/main.py` y la
convierte en una única Vercel Function. No hay servidor corriendo de forma
permanente: Vercel crea una instancia cuando llega un request y la descarta
cuando deja de recibir tráfico.
"""

import hmac
import logging
import os
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, ValidationError

from app import bot
from app.channels.telegram import TelegramClient, TelegramError, Update
from app.config import Settings, get_settings

# Vercel guarda en Runtime Logs todo lo que sale por stdout/stderr.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
# httpx loguea cada request con su URL en nivel INFO, y en la Bot API la URL
# contiene el token. Subirlo a WARNING evita filtrar el token en los logs.
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("bot-pdf")

ERROR_REPLY = "Tuve un problema procesando tu mensaje. Probá de nuevo en un rato."

app = FastAPI(
    title="bot-pdf",
    version="0.2.0",
    # Un bot no necesita documentación interactiva pública: menos superficie expuesta.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


# --- Dependencias (se pueden reemplazar en los tests con app.dependency_overrides)


def settings_dependency() -> Settings:
    try:
        return get_settings()
    except ValidationError as exc:
        # El detalle dice QUÉ variable falta, nunca valores.
        missing = ", ".join(str(err["loc"][0]).upper() for err in exc.errors())
        logger.error("Configuración incompleta. Faltan variables de entorno: %s", missing)
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, "Configuración incompleta") from None


SettingsDep = Annotated[Settings, Depends(settings_dependency)]


def telegram_dependency(settings: SettingsDep) -> TelegramClient:
    return TelegramClient(settings.telegram_bot_token.get_secret_value())


def verify_telegram_secret(
    settings: SettingsDep,
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> None:
    """Rechaza todo POST que no traiga el secreto que registramos en setWebhook.

    La URL del webhook es pública: sin este chequeo, cualquiera podría mandarnos
    Updates falsos y hacernos gastar cuota de Gemini. compare_digest compara en
    tiempo constante para no filtrar el secreto por diferencias de tiempo.
    """
    expected = settings.telegram_webhook_secret.get_secret_value()
    received = x_telegram_bot_api_secret_token or ""
    if not hmac.compare_digest(received.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Secreto inválido")


# --- Rutas


class HealthResponse(BaseModel):
    status: str
    commit: str
    region: str


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Chequeo de vida.

    `commit` permite confirmar que el deploy automático tomó el último push, y
    `region` que la función corre donde la configuramos. Vercel inyecta ambas
    variables en runtime; localmente valen "local".
    """
    return HealthResponse(
        status="ok",
        commit=os.getenv("VERCEL_GIT_COMMIT_SHA", "local")[:7],
        region=os.getenv("VERCEL_REGION", "local"),
    )


# La verificación va en `dependencies` para que corra ANTES de validar el body:
# un request sin secreto se rechaza sin siquiera parsearlo.
@app.post("/webhook", dependencies=[Depends(verify_telegram_secret)])
async def telegram_webhook(
    update: Update,
    telegram: Annotated[TelegramClient, Depends(telegram_dependency)],
) -> dict[str, bool]:
    """Recibe un Update de Telegram y responde al usuario.

    Una vez pasada la verificación, SIEMPRE devolvemos 200. Si devolviéramos un
    error, Telegram reintentaría el mismo Update una y otra vez, y el usuario
    recibiría respuestas duplicadas o el bot quedaría trabado en ese mensaje.
    Los errores se registran en los logs y al usuario le llega un aviso.
    """
    message = update.message
    # Ignoramos otros tipos de Update y los chats grupales: el bot es 1 a 1.
    if message is None or message.chat.type != "private":
        return {"ok": True}

    chat_id = message.chat.id
    user_id = message.from_user.id if message.from_user else chat_id

    try:
        await telegram.send_typing(chat_id)
    except TelegramError as exc:
        logger.warning("No se pudo mostrar 'escribiendo': %s", exc)

    try:
        reply = await bot.handle_text(user_id, message.text)
    except Exception:
        logger.exception("Error procesando el update %s", update.update_id)
        reply = ERROR_REPLY

    try:
        await telegram.send_message(chat_id, reply)
    except TelegramError as exc:
        logger.error("No se pudo responder al update %s: %s", update.update_id, exc)

    return {"ok": True}
