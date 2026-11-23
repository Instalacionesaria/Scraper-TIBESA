"""
Agente "Analista de Mercado": responde preguntas sobre TODAS las propiedades
guardadas usando las herramientas de `herramientas.py` (tool-calling).

El histórico de cada conversación lo guarda el checkpointer (`memoria.py`) bajo un
`thread_id`; el frontend solo manda el mensaje nuevo y el id de la conversación.
"""

import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from zoneinfo import ZoneInfo

import yaml
from langchain.agents import create_agent
from langchain.agents.middleware import ModelRequest, ModelResponse, dynamic_prompt, wrap_model_call
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage

from .herramientas import HERRAMIENTAS
from .memoria import obtener_checkpointer


DEFAULT_MODEL = "gpt-4.1"
TURNOS_EN_CONTEXTO = 6  # preguntas anteriores (con sus respuestas) que ve el modelo; el histórico completo queda guardado
PROMPT_PATH = Path(__file__).parent / "prompt" / "system_prompt.yaml"

_lock = threading.Lock()
_agente = None


@dynamic_prompt
def _prompt_con_fecha(request: ModelRequest) -> str:
    """El prompt se lee en cada llamada para que la fecha de hoy siempre sea la correcta."""
    cfg = yaml.safe_load(PROMPT_PATH.read_text(encoding="utf-8"))
    hoy = datetime.now(ZoneInfo("America/Mazatlan")).strftime("%d/%m/%Y")
    return cfg["system_prompt"].replace("{fecha_hoy}", hoy)


@wrap_model_call
def _recortar_contexto(request: ModelRequest, handler: Callable[[ModelRequest], ModelResponse]) -> ModelResponse:
    """Manda al modelo solo los últimos turnos. NO modifica el estado guardado:
    la conversación completa sigue en el checkpointer para mostrarla al usuario."""
    mensajes = request.messages
    humanos = [i for i, m in enumerate(mensajes) if isinstance(m, HumanMessage)]
    if len(humanos) > TURNOS_EN_CONTEXTO + 1:
        desde = humanos[-(TURNOS_EN_CONTEXTO + 1)]  # empieza en una pregunta: no corta pares tool_call/tool
        request = request.override(messages=mensajes[desde:])
    return handler(request)


def _obtener_agente():
    global _agente
    with _lock:
        if _agente is None:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise RuntimeError("OPENAI_API_KEY no configurada en el backend.")
            model_name = os.getenv("ANALISTA_MERCADO_MODEL") or DEFAULT_MODEL
            llm = init_chat_model(model_name, model_provider="openai", api_key=api_key, temperature=0.2)
            _agente = create_agent(
                model=llm,
                tools=HERRAMIENTAS,
                middleware=[_prompt_con_fecha, _recortar_contexto],
                checkpointer=obtener_checkpointer(),
            )
        return _agente


def _config(thread_id: str, usuario: Optional[str] = None) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {"configurable": {"thread_id": thread_id}, "recursion_limit": 16}
    if usuario:
        cfg["metadata"] = {"usuario": usuario}  # queda en cada checkpoint: permite listar sus conversaciones
    return cfg


def _texto(mensaje) -> str:
    contenido = mensaje.content
    if isinstance(contenido, list):
        return "".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in contenido)
    return str(contenido or "")


def responder(thread_id: str, mensaje: str, usuario: Optional[str] = None) -> str:
    """Agrega la pregunta a la conversación `thread_id` y devuelve la respuesta final."""
    resultado = _obtener_agente().invoke(
        {"messages": [{"role": "user", "content": mensaje}]},
        config=_config(thread_id, usuario),
    )
    return _texto(resultado["messages"][-1])


def mensajes_de(thread_id: str) -> List[Dict[str, str]]:
    """Conversación visible (preguntas y respuestas finales, sin pasos internos de herramientas)."""
    estado = _obtener_agente().get_state(_config(thread_id))
    salida = []
    for m in (estado.values or {}).get("messages", []):
        if isinstance(m, HumanMessage):
            salida.append({"role": "user", "content": _texto(m)})
        elif isinstance(m, AIMessage) and not m.tool_calls and _texto(m).strip():
            salida.append({"role": "assistant", "content": _texto(m)})
    return salida
