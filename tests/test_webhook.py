from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app import bot
from app.channels.telegram import TelegramError
from app.config import Settings
from app.main import app, settings_dependency, telegram_dependency

SECRET = "secreto-de-prueba"
HEADERS = {"X-Telegram-Bot-Api-Secret-Token": SECRET}


class FakeTelegram:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[int, str]] = []
        self.fail = fail

    async def send_typing(self, chat_id: int) -> None:
        return None

    async def send_message(self, chat_id: int, text: str) -> None:
        if self.fail:
            raise TelegramError("sendMessage: HTTP 400 - chat not found")
        self.sent.append((chat_id, text))


@pytest.fixture
def fake() -> FakeTelegram:
    return FakeTelegram()


@pytest.fixture
def client(fake: FakeTelegram) -> Iterator[TestClient]:
    app.dependency_overrides[settings_dependency] = lambda: Settings(
        telegram_bot_token="123:abc", telegram_webhook_secret=SECRET
    )
    app.dependency_overrides[telegram_dependency] = lambda: fake
    yield TestClient(app)
    app.dependency_overrides.clear()


def update(text: str | None = "hola", chat_type: str = "private") -> dict[str, object]:
    message: dict[str, object] = {
        "message_id": 1,
        "chat": {"id": 42, "type": chat_type},
        "from": {"id": 7, "first_name": "Ana", "is_bot": False},
        "date": 0,
    }
    if text is not None:
        message["text"] = text
    return {"update_id": 1000, "message": message}


def test_rechaza_sin_secreto(client: TestClient, fake: FakeTelegram) -> None:
    response = client.post("/webhook", json=update())
    assert response.status_code == 401
    assert fake.sent == []


def test_rechaza_secreto_incorrecto(client: TestClient, fake: FakeTelegram) -> None:
    response = client.post("/webhook", json=update(), headers={"X-Telegram-Bot-Api-Secret-Token": "x"})
    assert response.status_code == 401
    assert fake.sent == []


def test_rechaza_antes_de_validar_el_body(client: TestClient) -> None:
    # Sin secreto ni body válido: debe ser 401, no 422.
    assert client.post("/webhook", json={"basura": True}).status_code == 401


def test_start(client: TestClient, fake: FakeTelegram) -> None:
    response = client.post("/webhook", json=update("/start"), headers=HEADERS)
    assert response.status_code == 200
    assert fake.sent == [(42, bot.WELCOME)]


def test_pregunta_responde_eco(client: TestClient, fake: FakeTelegram) -> None:
    client.post("/webhook", json=update("¿Qué dice el capítulo 2?"), headers=HEADERS)
    assert len(fake.sent) == 1
    assert "¿Qué dice el capítulo 2?" in fake.sent[0][1]


def test_mensaje_sin_texto(client: TestClient, fake: FakeTelegram) -> None:
    client.post("/webhook", json=update(text=None), headers=HEADERS)
    assert fake.sent == [(42, bot.ONLY_TEXT)]


def test_ignora_grupos(client: TestClient, fake: FakeTelegram) -> None:
    response = client.post("/webhook", json=update(chat_type="group"), headers=HEADERS)
    assert response.status_code == 200
    assert fake.sent == []


def test_ignora_updates_sin_message(client: TestClient, fake: FakeTelegram) -> None:
    response = client.post("/webhook", json={"update_id": 1, "edited_message": {}}, headers=HEADERS)
    assert response.status_code == 200
    assert fake.sent == []


def test_error_interno_devuelve_200_y_avisa(
    client: TestClient, fake: FakeTelegram, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def explota(user_id: int, text: str | None) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(bot, "handle_text", explota)
    response = client.post("/webhook", json=update(), headers=HEADERS)
    assert response.status_code == 200  # si no, Telegram reintenta en loop
    assert fake.sent[0][1].startswith("Tuve un problema")


def test_falla_al_enviar_igual_devuelve_200(client: TestClient) -> None:
    app.dependency_overrides[telegram_dependency] = lambda: FakeTelegram(fail=True)
    response = client.post("/webhook", json=update(), headers=HEADERS)
    assert response.status_code == 200


def test_falta_configuracion_devuelve_500(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    get_settings.cache_clear()
    response = TestClient(app).post("/webhook", json=update(), headers=HEADERS)
    assert response.status_code == 500
    get_settings.cache_clear()
