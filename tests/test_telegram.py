import asyncio
import json

import httpx
import pytest

from app.channels.telegram import TelegramClient, TelegramError, split_message

TOKEN = "123456:TOKEN-SUPER-SECRETO"


def test_split_mensaje_corto() -> None:
    assert split_message("hola") == ["hola"]


def test_split_respeta_limite_y_no_pierde_texto() -> None:
    text = "\n".join(f"línea {i}" for i in range(2000))
    chunks = split_message(text, limit=100)
    assert all(len(c) <= 100 for c in chunks)
    assert "\n".join(chunks) == text


def test_split_sin_saltos_de_linea() -> None:
    chunks = split_message("x" * 250, limit=100)
    assert [len(c) for c in chunks] == [100, 100, 50]


def test_send_message_arma_el_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"ok": True, "result": {}})

    client = TelegramClient(TOKEN, transport=httpx.MockTransport(handler))
    asyncio.run(client.send_message(42, "hola"))

    assert requests[0].url.path == f"/bot{TOKEN}/sendMessage"
    assert json.loads(requests[0].content) == {"chat_id": 42, "text": "hola"}


def test_error_de_api_no_filtra_el_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    client = TelegramClient(TOKEN, transport=httpx.MockTransport(handler))
    with pytest.raises(TelegramError) as info:
        asyncio.run(client.send_message(42, "hola"))

    assert "chat not found" in str(info.value)
    assert TOKEN not in str(info.value)


def test_error_de_red_no_filtra_el_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"falló la conexión a {request.url}")

    client = TelegramClient(TOKEN, transport=httpx.MockTransport(handler))
    with pytest.raises(TelegramError) as info:
        asyncio.run(client.send_message(42, "hola"))

    assert TOKEN not in str(info.value)
    assert info.value.__cause__ is None  # tampoco queda encadenada la excepción original
