"""
Asistente conversacional que ayuda a llenar el formulario del Scraper de LinkedIn.

El usuario describe en lenguaje natural (español) qué leads busca y el LLM
devuelve una respuesta corta + los valores de los campos del formulario
(Job Title, Country, State, Number of Leads) en el formato que espera el actor
de Apify (nombres en inglés). El asistente NUNCA lanza el scrapeo: solo llena
los campos; el usuario revisa y da clic en "Iniciar Scraping".
"""

import os
from typing import List, Literal, Optional

from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field


DEFAULT_MODEL = "gpt-4.1"
MAX_HISTORIAL = 20  # últimos mensajes que se mandan al LLM
MAX_LEADS = 30000

SYSTEM_PROMPT = """Eres el asistente del "Scraper de LinkedIn" de TIBESA Bienes Raíces (Mazatlán, México).
Tu único trabajo es ayudar al usuario (personas no técnicas, p.ej. Don Bernardo) a llenar el formulario
de búsqueda de leads. Hablas SIEMPRE en español, en tono cordial, breve y claro (máx. 3-4 frases).

CAMPOS DEL FORMULARIO (los valores SIEMPRE en inglés, que es lo que entiende el buscador):
- job_title (obligatorio): cargo/puesto en LinkedIn, en inglés. Ej: "Real Estate Agent", "Real Estate Broker",
  "Property Manager", "Real Estate Investor", "CEO", "Architect", "General Contractor".
  Si el usuario lo dice en español, tradúcelo (corredor inmobiliario → "Real Estate Broker";
  asesor/agente inmobiliario → "Real Estate Agent"; inversionista → "Real Estate Investor";
  constructor → "General Contractor"; desarrollador inmobiliario → "Real Estate Developer").
- country (obligatorio): país en inglés. Ej: "United States", "Canada", "Mexico".
- state (opcional): estado/provincia en inglés tal como lo usa LinkedIn/Apollo. Ej: "California", "Texas",
  "Arizona", "British Columbia", "Ontario", "Sinaloa", "Jalisco", "Mexico City" (para CDMX).
  Debe pertenecer al país elegido. Usa "" (cadena vacía) solo si el usuario pide quitar el estado.
- number_of_leads (obligatorio): entero entre 1 y 30000. Si el usuario no lo dice, sugiere 100.
  Avisa que más leads = más tiempo y más costo.

REGLAS:
- En `campos` devuelve SOLO los campos que quieras poner o cambiar; deja en null los que no cambian.
- Considera los VALORES ACTUALES del formulario (te los paso abajo) para no repetir ni pisar datos sin motivo.
- Si falta un dato obligatorio, pregúntalo de forma concreta (una sola pregunta a la vez).
- Si el usuario es ambiguo (p.ej. "gringos"), interpreta lo más razonable (United States) y dilo.
- `listo` = true cuando job_title, country y number_of_leads queden completos.
  Entonces dile que revise los campos y presione el botón azul "Iniciar Scraping".
- Tú NO inicias el scrapeo ni prometes resultados; no inventes cantidades de leads disponibles.
- Si preguntan algo fuera de este formulario, redirige amablemente a la búsqueda de leads.

VALORES ACTUALES DEL FORMULARIO:
{valores_actuales}
"""


class MensajeChat(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class CamposLinkedIn(BaseModel):
    job_title: Optional[str] = Field(None, description="Cargo en inglés, o null si no cambia")
    country: Optional[str] = Field(None, description="País en inglés, o null si no cambia")
    state: Optional[str] = Field(None, description="Estado en inglés, '' para quitarlo, o null si no cambia")
    number_of_leads: Optional[int] = Field(None, description="Entero 1-30000, o null si no cambia")


class RespuestaAsistente(BaseModel):
    respuesta: str = Field(..., description="Mensaje para el usuario, en español")
    campos: CamposLinkedIn
    listo: bool = Field(..., description="True si los campos obligatorios ya están completos")


def _formatear_valores(actuales: dict) -> str:
    etiquetas = {
        "jobTitle": "job_title",
        "country": "country",
        "state": "state",
        "numberOfLeads": "number_of_leads",
    }
    lineas = []
    for clave, nombre in etiquetas.items():
        valor = actuales.get(clave)
        lineas.append(f"- {nombre}: {valor if valor not in (None, '') else '(vacío)'}")
    return "\n".join(lineas)


def responder(mensajes: List[MensajeChat], valores_actuales: dict) -> RespuestaAsistente:
    """Llama al LLM con el historial y devuelve respuesta + campos sugeridos."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY no configurada en el backend.")

    model_name = os.getenv("LINKEDIN_ASISTENTE_MODEL", DEFAULT_MODEL)
    llm = init_chat_model(model_name, model_provider="openai", api_key=api_key, temperature=0.2)
    llm_estructurado = llm.with_structured_output(RespuestaAsistente)

    historial = [SystemMessage(content=SYSTEM_PROMPT.format(valores_actuales=_formatear_valores(valores_actuales)))]
    for m in mensajes[-MAX_HISTORIAL:]:
        historial.append(HumanMessage(content=m.content) if m.role == "user" else AIMessage(content=m.content))

    resultado: RespuestaAsistente = llm_estructurado.invoke(historial)

    # Saneamos lo que vuelve del LLM antes de mandarlo al formulario.
    c = resultado.campos
    if c.number_of_leads is not None:
        c.number_of_leads = max(1, min(MAX_LEADS, int(c.number_of_leads)))
    for attr in ("job_title", "country", "state"):
        valor = getattr(c, attr)
        if isinstance(valor, str):
            setattr(c, attr, valor.strip())
    return resultado
