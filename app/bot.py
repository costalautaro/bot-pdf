"""Lógica del bot, independiente del canal.

Recibe el texto del usuario y devuelve el texto de la respuesta. No sabe nada
de Telegram: el adaptador del canal se encarga de recibir y enviar.
En la Fase 4 `answer_question` pasa a usar RAG; en la Fase 5, /reset borra la
memoria guardada en Supabase.
"""

WELCOME = (
    "¡Hola! Respondo preguntas usando solo la información de un documento PDF.\n\n"
    "Escribime tu pregunta. Comandos:\n"
    "/start - ver este mensaje\n"
    "/reset - borrar el historial de la conversación"
)
RESET_DONE = "Listo, empezamos una conversación nueva."
ONLY_TEXT = "Por ahora solo entiendo mensajes de texto."
UNKNOWN_COMMAND = "No conozco ese comando. Probá con /start o /reset."


def parse_command(text: str) -> str | None:
    """Devuelve el comando en minúsculas ("/start") o None si no es un comando.

    En grupos Telegram agrega el username del bot: "/start@mi_bot" → "/start".
    """
    if not text.startswith("/"):
        return None
    return text.split(maxsplit=1)[0].split("@", 1)[0].lower()


async def handle_text(user_id: int, text: str | None) -> str:
    if not text:
        return ONLY_TEXT

    command = parse_command(text)
    if command == "/start":
        return WELCOME
    if command == "/reset":
        # Fase 5: borrar el historial de user_id en Supabase.
        return RESET_DONE
    if command is not None:
        return UNKNOWN_COMMAND

    return await answer_question(user_id, text)


async def answer_question(user_id: int, question: str) -> str:
    # Fase 4: buscar fragmentos en Supabase y preguntarle a Gemini.
    return f"Recibí tu pregunta: «{question}»\n\n(Todavía no leo el PDF: eso llega en la Fase 4.)"
