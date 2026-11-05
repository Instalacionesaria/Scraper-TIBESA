"""
Núcleo compartido de los asistentes IA que llenan formularios de búsqueda.

Cada asistente (LinkedIn, Búsqueda de Leads, ...) define su system prompt y su
esquema Pydantic de respuesta; aquí vive la llamada al LLM con salida
estructurada y el modelo de mensaje del chat.
"""

import os
from typing import List, Literal, Type, TypeVar

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel


DEFAULT_MODEL = "gpt-4.1"
MAX_HISTORIAL = 20  # últimos mensajes que se mandan al LLM

T = TypeVar("T", bound=BaseModel)


class MensajeChat(BaseModel):
    role: Literal["user", "assistant"]
    content: str


def invocar_estructurado(system_prompt: str, esquema: Type[T], mensajes: List[MensajeChat]) -> T:
    """Llama al LLM con el historial y devuelve una instancia de `esquema`."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY no configurada en el backend.")

    model_name = os.getenv("ASISTENTE_IA_MODEL") or os.getenv("LINKEDIN_ASISTENTE_MODEL") or DEFAULT_MODEL
    llm = init_chat_model(model_name, model_provider="openai", api_key=api_key, temperature=0.2)

    historial = [SystemMessage(content=system_prompt)]
    for m in mensajes[-MAX_HISTORIAL:]:
        historial.append(HumanMessage(content=m.content) if m.role == "user" else AIMessage(content=m.content))

    return llm.with_structured_output(esquema).invoke(historial)


def formatear_valores(actuales: dict, etiquetas: dict) -> str:
    """Convierte los valores actuales del formulario en texto para el prompt."""
    lineas = []
    for clave, nombre in etiquetas.items():
        valor = actuales.get(clave)
        lineas.append(f"- {nombre}: {valor if valor not in (None, '') else '(vacío)'}")
    return "\n".join(lineas)
