"""Adaptador del canal Telegram: modelos del Update y cliente de la Bot API.

Todo lo específico de Telegram vive acá. El resto de la app trabaja con texto
plano y un identificador de conversación, así que sumar otro canal (por ejemplo
WhatsApp) sería escribir otro adaptador sin tocar la lógica del bot.

Referencia: https://core.telegram.org/bots/api
"""

import logging

import httpx
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
# Límite de la Bot API para el texto de un mensaje.
MAX_MESSAGE_LENGTH = 4096


# --- Modelos: solo los campos que usamos. Telegram agrega campos nuevos seguido,
# por eso extra="ignore": un campo desconocido no debe romper el webhook.


class _TelegramModel(BaseModel):
    model_config = ConfigDict(extra="ignore", populate_by_name=True)


class User(_TelegramModel):
    id: int
    first_name: str = ""


class Chat(_TelegramModel):
    id: int
    type: str  # "private", "group", "supergroup" o "channel"


class Message(_TelegramModel):
    message_id: int
    chat: Chat
    # "from" es palabra reservada en Python, por eso el alias.
    from_user: User | None = Field(default=None, alias="from")
    text: str | None = None


class Update(_TelegramModel):
    """Lo que Telegram nos manda por POST en cada evento.

    Un Update trae exactamente UNO de muchos campos opcionales (message,
    edited_message, callback_query, ...). Solo nos interesa `message`; lo demás
    lo filtramos también al registrar el webhook con allowed_updates.
    """

    update_id: int
    message: Message | None = None


# --- Cliente


class TelegramError(Exception):
    """Falla al llamar a la Bot API. El mensaje nunca incluye el token."""


def split_message(text: str, limit: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """Parte un texto largo en trozos que Telegram acepte, cortando en saltos de línea."""
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(text[:cut])
        text = text[cut:].lstrip("\n")
    if text:
        chunks.append(text)
    return chunks


class TelegramClient:
    def __init__(
        self,
        token: str,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,  # para inyectar un fake en tests
    ) -> None:
        self._base_url = f"{TELEGRAM_API}/bot{token}"
        self._timeout = timeout
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout, transport=self._transport
        )

    async def send_message(self, chat_id: int, text: str) -> None:
        """Envía texto plano (sin parse_mode).

        Con parse_mode=Markdown, un `_` o `*` sin cerrar en la respuesta del LLM
        hace que Telegram rechace el mensaje entero. Texto plano nunca falla por eso.
        """
        async with self._client() as client:
            for chunk in split_message(text):
                await self._call(client, "sendMessage", {"chat_id": chat_id, "text": chunk})

    async def send_typing(self, chat_id: int) -> None:
        """Muestra "escribiendo..." en el chat durante unos segundos."""
        async with self._client() as client:
            await self._call(client, "sendChatAction", {"chat_id": chat_id, "action": "typing"})

    @staticmethod
    async def _call(client: httpx.AsyncClient, method: str, payload: dict[str, object]) -> None:
        try:
            response = await client.post(f"/{method}", json=payload)
        except httpx.HTTPError as exc:
            # str(exc) puede incluir la URL, y la URL incluye el token: solo el tipo.
            raise TelegramError(f"{method}: error de red ({type(exc).__name__})") from None
        try:
            data = response.json()
        except ValueError:  # p. ej. una página HTML de error de un proxy
            data = {}
        if response.status_code != 200 or not data.get("ok"):
            # La Bot API explica el error en "description" (ej. "chat not found").
            raise TelegramError(
                f"{method}: HTTP {response.status_code} - {data.get('description', 'sin detalle')}"
            )
