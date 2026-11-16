"""Punto de entrada de la aplicación.

Vercel detecta automáticamente la instancia `app` en `app/main.py` y la
convierte en una única Vercel Function. No hay servidor corriendo de forma
permanente: Vercel crea una instancia cuando llega un request y la descarta
cuando deja de recibir tráfico.
"""

import os

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="bot-pdf",
    version="0.1.0",
    # Un bot no necesita documentación interactiva pública: menos superficie expuesta.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)


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
