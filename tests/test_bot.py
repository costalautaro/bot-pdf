import asyncio

import pytest

from app import bot


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("/start", "/start"),
        ("/START", "/start"),
        ("/start@mi_bot", "/start"),
        ("/reset ahora", "/reset"),
        ("hola", None),
        ("¿qué es /start?", None),
    ],
)
def test_parse_command(text: str, expected: str | None) -> None:
    assert bot.parse_command(text) == expected


def test_comando_desconocido() -> None:
    assert asyncio.run(bot.handle_text(1, "/foo")) == bot.UNKNOWN_COMMAND


def test_reset() -> None:
    assert asyncio.run(bot.handle_text(1, "/reset")) == bot.RESET_DONE
