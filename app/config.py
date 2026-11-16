"""Configuración leída de variables de entorno.

En producción las variables las inyecta Vercel (Settings → Environment
Variables). Nunca se escriben en el código ni se suben al repo.
"""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    # SecretStr evita que el valor aparezca si alguien hace print/log del objeto:
    # se muestra como '**********'. Para usarlo hay que llamar .get_secret_value().
    telegram_bot_token: SecretStr
    telegram_webhook_secret: SecretStr


@lru_cache
def get_settings() -> Settings:
    """Lee y valida las variables una sola vez por instancia.

    Es perezoso a propósito: si falta una variable, falla el endpoint que la
    necesita (con un error claro en los logs), no el import de toda la app.
    Así /health sigue respondiendo y el diagnóstico es más fácil.
    """
    return Settings()  # type: ignore[call-arg]  # los valores vienen del entorno
