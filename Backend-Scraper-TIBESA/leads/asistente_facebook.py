"""
Asistente conversacional que ayuda a llenar el formulario de "Scrappers de Facebook".

El usuario describe en español qué anunciantes busca (p. ej. "inmobiliarias que
anuncian en México") y el LLM devuelve una respuesta corta + palabra clave, país,
si solo anuncios activos y una etiqueta para el CRM. Con eso el backend arma la
URL de la Biblioteca de Anuncios de Facebook (no la arma el LLM, para que siempre
sea válida). NUNCA lanza el scrapeo: solo llena los campos.
"""

from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo
from urllib.parse import parse_qs, urlencode, urlparse

from pydantic import BaseModel, Field

from .asistente_ia import MensajeChat, invocar_estructurado


BASE_URL_BIBLIOTECA = "https://www.facebook.com/ads/library/"
MAX_ETIQUETA_LEN = 30
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

SYSTEM_PROMPT = """Eres el asistente de "Scrappers de Facebook" de TIBESA Bienes Raíces (Mazatlán, Sinaloa, México).
Esta herramienta busca en la Biblioteca de Anuncios de Facebook a los NEGOCIOS/PÁGINAS que están pagando anuncios
sobre un tema, y luego saca los datos de contacto de esas páginas (leads).
Tu único trabajo es ayudar al usuario (persona no técnica, p. ej. Don Bernardo, ~70 años) a llenar el formulario.
Hablas SIEMPRE en español, tratando al usuario de "usted", en tono cordial, breve y claro (máx. 3-4 frases).

CAMPOS QUE DEBES DEFINIR:
- palabra_clave (obligatorio): lo que se escribiría en el buscador de la Biblioteca de Anuncios. Corta (1-4 palabras),
  en el idioma de los anuncios que se buscan. Ej: "bienes raíces", "inmobiliaria", "venta de terrenos",
  "departamentos Mazatlán", "preventa", "casas en venta", "real estate" (si busca anunciantes de EE. UU./Canadá).
  Si el usuario menciona una ciudad, inclúyela en la palabra clave (Facebook no filtra por ciudad).
- pais (obligatorio): código ISO de 2 letras del país donde se muestran los anuncios. Ej: "MX" (México),
  "US" (Estados Unidos), "CA" (Canadá), "ES" (España). Usa "ALL" solo si pide todos los países.
  Si no lo dice, usa "MX" y menciónalo.
- solo_activos (opcional, true/false): true = solo anuncios que están corriendo ahora (negocios activos, recomendado);
  false = también anuncios viejos. Si no lo menciona, déjalo en null (por defecto se usan solo activos).
- etiqueta (opcional): nombre corto para identificar estos leads en el CRM de TIBESA, MÁXIMO 30 caracteres.
  Si pones mes o año, usa la FECHA DE HOY (abajo), nunca otro año. Ej: "FB Inmobiliarias MX - {mes_anio}".
  Propónla tú cuando ya tengas palabra clave y país, si está vacía.

REGLAS:
- En `campos` devuelve SOLO los campos que quieras poner o cambiar; deja en null los que no cambian.
- Considera los VALORES ACTUALES del formulario (te los paso abajo) para no pisar datos sin motivo.
- Si falta un dato obligatorio, pregúntalo de forma concreta (una sola pregunta a la vez).
- `listo` = true cuando palabra_clave y pais queden completos. Entonces dígale que revise la URL y presione el botón
  azul "Iniciar scraping de esta biblioteca de anuncios". Después, cuando termine, debe presionar el segundo botón
  "Iniciar Scraping de las Páginas de Facebook" para obtener los datos de contacto.
- Tú NO inicias el scrapeo ni prometes resultados; no inventes cuántas páginas o leads saldrán.
- Una palabra clave muy específica puede dar pocos anunciantes; para más volumen sugiere una más general.
- Si el usuario pega una URL de la Biblioteca de Anuncios, dígale que ya puede usarla tal cual y no cambie nada.
- Si preguntan algo fuera de este formulario, redirige amablemente a la búsqueda de anunciantes.

FECHA DE HOY: {hoy}

VALORES ACTUALES DEL FORMULARIO:
{valores_actuales}
"""


class CamposFacebookLLM(BaseModel):
    palabra_clave: Optional[str] = Field(None, description="Texto a buscar en la Biblioteca de Anuncios, o null si no cambia")
    pais: Optional[str] = Field(None, description="Código ISO-2 del país (MX, US, ...) o 'ALL', o null si no cambia")
    solo_activos: Optional[bool] = Field(None, description="True = solo anuncios activos; null si no cambia")
    etiqueta: Optional[str] = Field(None, description="Etiqueta para el CRM (máx. 30 caracteres), o null si no cambia")


class RespuestaLLM(BaseModel):
    respuesta: str = Field(..., description="Mensaje para el usuario, en español, tratándolo de usted")
    campos: CamposFacebookLLM
    listo: bool = Field(..., description="True si palabra_clave y pais ya están completos")


class CamposFacebook(BaseModel):
    url_biblioteca: Optional[str] = None
    etiqueta: Optional[str] = None
    palabra_clave: Optional[str] = None
    pais: Optional[str] = None


class RespuestaAsistente(BaseModel):
    respuesta: str
    campos: CamposFacebook
    listo: bool


def _leer_url(url: str) -> dict:
    """Extrae palabra clave, país y estado de una URL de la Biblioteca de Anuncios (si lo es)."""
    try:
        partes = urlparse(url or "")
    except ValueError:
        return {}
    if "facebook.com" not in partes.netloc or "/ads/library" not in partes.path:
        return {}
    qs = parse_qs(partes.query)
    return {
        "palabra_clave": (qs.get("q") or [None])[0],
        "pais": (qs.get("country") or [None])[0],
        "solo_activos": (qs.get("active_status") or ["active"])[0] == "active",
    }


def construir_url(palabra_clave: str, pais: str, solo_activos: bool = True) -> str:
    """Arma la URL de búsqueda por palabra clave de la Biblioteca de Anuncios de Facebook."""
    params = {
        "active_status": "active" if solo_activos else "all",
        "ad_type": "all",
        "country": pais,
        "is_targeted_country": "false",
        "media_type": "all",
        "q": palabra_clave,
        "search_type": "keyword_unordered",
    }
    return f"{BASE_URL_BIBLIOTECA}?{urlencode(params)}"


def responder(mensajes: List[MensajeChat], valores_actuales: dict) -> RespuestaAsistente:
    """Llama al LLM con el historial y devuelve respuesta + campos del formulario."""
    url_actual = (valores_actuales.get("urlBiblioteca") or "").strip()
    etiqueta_actual = (valores_actuales.get("etiqueta") or "").strip()
    previo = _leer_url(url_actual)

    valores_txt = "\n".join([
        f"- URL de la biblioteca: {url_actual or '(vacío)'}",
        f"- palabra_clave (según la URL): {previo.get('palabra_clave') or '(vacío)'}",
        f"- pais (según la URL): {previo.get('pais') or '(vacío)'}",
        f"- etiqueta: {etiqueta_actual or '(vacío)'}",
    ])
    ahora = datetime.now(ZoneInfo("America/Mazatlan"))
    mes_anio = f"{MESES[ahora.month - 1]} {ahora.year}"
    prompt = SYSTEM_PROMPT.format(valores_actuales=valores_txt, hoy=ahora.strftime("%d/%m/%Y"), mes_anio=mes_anio)
    resultado = invocar_estructurado(prompt, RespuestaLLM, mensajes)
    c = resultado.campos

    # Combinamos lo nuevo con lo que ya había y armamos la URL nosotros.
    palabra = (c.palabra_clave or "").strip() or previo.get("palabra_clave")
    pais = (c.pais or "").strip().upper() or previo.get("pais")
    if pais and pais != "ALL" and len(pais) != 2:
        pais = None
    solo_activos = c.solo_activos if c.solo_activos is not None else previo.get("solo_activos", True)

    salida = CamposFacebook()
    cambio_busqueda = c.palabra_clave is not None or c.pais is not None or c.solo_activos is not None
    if palabra and pais and cambio_busqueda:
        salida.url_biblioteca = construir_url(palabra, pais, solo_activos)
        salida.palabra_clave = palabra
        salida.pais = pais
    if c.etiqueta:
        salida.etiqueta = c.etiqueta.strip()[:MAX_ETIQUETA_LEN]

    return RespuestaAsistente(respuesta=resultado.respuesta, campos=salida, listo=resultado.listo)
