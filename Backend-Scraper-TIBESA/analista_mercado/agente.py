"""
Agente "Analista de Mercado": responde preguntas sobre TODAS las propiedades
guardadas usando las herramientas de `herramientas.py` (tool-calling).

Es stateless: el frontend manda el historial de la conversación en cada petición.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import List, Literal
from zoneinfo import ZoneInfo

import yaml
from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from pydantic import BaseModel

from .herramientas import HERRAMIENTAS


DEFAULT_MODEL = "gpt-4.1"
MAX_HISTORIAL = 12  # últimos mensajes que se mandan al agente
PROMPT_PATH = Path(__file__).parent / "prompt" / "system_prompt.yaml"


class MensajeChat(BaseModel):
    role: Literal["user", "assistant"]
    content: str


def _system_prompt() -> str:
    cfg = yaml.safe_load(PROMPT_PATH.read_text(encoding="utf-8"))
    hoy = datetime.now(ZoneInfo("America/Mazatlan")).strftime("%d/%m/%Y")
    return cfg["system_prompt"].replace("{fecha_hoy}", hoy)


def _crear_agente():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY no configurada en el backend.")
    model_name = os.getenv("ANALISTA_MERCADO_MODEL") or DEFAULT_MODEL
    llm = init_chat_model(model_name, model_provider="openai", api_key=api_key, temperature=0.2)
    return create_agent(model=llm, tools=HERRAMIENTAS, system_prompt=_system_prompt())


def responder(mensajes: List[MensajeChat]) -> str:
    """Ejecuta el agente con el historial y devuelve el texto de la respuesta final."""
    agente = _crear_agente()  # barato; así la fecha del prompt siempre es la de hoy
    historial = [{"role": m.role, "content": m.content} for m in mensajes[-MAX_HISTORIAL:]]
    resultado = agente.invoke({"messages": historial}, config={"recursion_limit": 16})
    return resultado["messages"][-1].content
