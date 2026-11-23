"""
Informe de Mercado en PDF a partir de una conversación del Analista de Mercado.

1. Junta las respuestas de la conversación y los GRÁFICOS calculados por las
   herramientas (visualizaciones.py) — las cifras de tablas y gráficos salen de ahí.
2. Un LLM redacta el informe por temas (prompt/informe_prompt.yaml) con salida
   estructurada: resumen ejecutivo, secciones (con ids de gráficos) y recomendaciones.
3. Se renderiza templates/informe.html con Jinja2 y Chromium (Playwright) lo pasa a PDF A4.
4. Se guarda en data/informes/ (volumen persistente) con un .json de metadatos para
   listarlo en "Resultados".
"""

import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from langchain.chat_models import init_chat_model
from playwright.async_api import async_playwright
from pydantic import BaseModel, Field

from utils.zona_horaria import ahora_mazatlan

from . import agente
from .datos import TIPO_CAMBIO_USD_MXN
from .visualizaciones import panorama

BASE = Path(__file__).parent
PROMPT_PATH = BASE / "prompt" / "informe_prompt.yaml"
TEMPLATES_DIR = BASE / "templates"
LOGO_PATH = BASE.parent / "brochure" / "static" / "tibesa-logo.png"
INFORMES_DIR = Path("data") / "informes"
DEFAULT_MODEL = "gpt-4.1"
MAX_CONVERSACION = 40000  # caracteres de conversación que se mandan al LLM
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
         "septiembre", "octubre", "noviembre", "diciembre"]


class SeccionInforme(BaseModel):
    titulo: str = Field(..., description="Nombre del tema")
    texto: str = Field(..., description="1 a 3 párrafos en texto plano separados por línea en blanco")
    graficos: List[int] = Field(default_factory=list, description="ids del catálogo de gráficos (0 a 2)")


class InformeLLM(BaseModel):
    titulo: str
    subtitulo: str
    resumen_ejecutivo: List[str] = Field(..., description="3 a 5 conclusiones, una oración cada una")
    secciones: List[SeccionInforme]
    recomendaciones: List[str] = Field(default_factory=list)


def _fecha_larga(d: datetime) -> str:
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _catalogo(mensajes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Gráficos de todas las respuestas, sin repetir: dos gráficos con el mismo título pero datos distintos
    (p. ej. "Precio típico de casas por zona" del ranking y de una comparación) se conservan ambos."""
    vistos: Dict[tuple, Dict[str, Any]] = {}
    for m in mensajes:
        for g in m.get("graficos") or []:
            etiquetas = tuple(f.get("etiqueta") for f in g.get("filas") or []) or \
                tuple(it.get("etiqueta") for it in g.get("items") or []) or \
                tuple(p.get("url") for p in g.get("puntos") or [])
            vistos[(g["tipo"], g["titulo"], etiquetas)] = g
    return list(vistos.values())


def _resumen_grafico(i: int, g: Dict[str, Any]) -> str:
    if g["tipo"] == "barras":
        filas = "; ".join(f"{f['etiqueta']}: {f['valor']:,.0f} {g.get('unidad', '')}" for f in g["filas"][:12])
        return f"[{i}] Barras «{g['titulo']}» ({g.get('orden', '')}): {filas}"
    if g["tipo"] == "cifras":
        items = "; ".join(f"{it['etiqueta']}: {it['valor']:,.0f} {it.get('unidad') or ''}".strip()
                          for it in g["items"] if it.get("valor") is not None)
        return f"[{i}] Cifras «{g['titulo']}»: {items}"
    props = "; ".join(f"{p.get('titulo', '')[:50]} ({p.get('precio') or 0:,.0f} MXN, {p.get('m2') or '?'} m²)"
                      for p in g["puntos"][:8])
    return f"[{i}] Propiedades «{g['titulo']}»: {props}"


def _conversacion_txt(mensajes: List[Dict[str, Any]]) -> str:
    partes = []
    for m in mensajes:
        quien = "PREGUNTA" if m["role"] == "user" else "RESPUESTA"
        partes.append(f"{quien}:\n{m['content']}")
    texto = "\n\n".join(partes)
    return texto[-MAX_CONVERSACION:]


def _redactar(mensajes: List[Dict[str, Any]], catalogo: List[Dict[str, Any]]) -> InformeLLM:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY no configurada en el backend.")
    cfg = yaml.safe_load(PROMPT_PATH.read_text(encoding="utf-8"))
    prompt = (cfg["system_prompt"]
              .replace("{fecha_hoy}", _fecha_larga(ahora_mazatlan()))
              .replace("{conversacion}", _conversacion_txt(mensajes))
              .replace("{catalogo_graficos}", "\n".join(_resumen_grafico(i, g) for i, g in enumerate(catalogo)) or "(sin gráficos)"))
    model_name = os.getenv("ANALISTA_MERCADO_MODEL") or DEFAULT_MODEL
    llm = init_chat_model(model_name, model_provider="openai", api_key=api_key, temperature=0.2)
    return llm.with_structured_output(InformeLLM).invoke([
        {"role": "system", "content": prompt},
        {"role": "user", "content": "Redacta el informe de mercado con la estructura indicada."},
    ])


def _slug(texto: str) -> str:
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return re.sub(r"[^A-Za-z0-9]+", "-", texto).strip("-")[:50] or "Informe"


def _formato_valor(valor: Optional[float], unidad: Optional[str]) -> str:
    if valor is None:
        return "Sin datos"
    if not unidad or unidad == "propiedades":
        return f"{valor:,.0f}"
    if not unidad.startswith("MXN"):
        return f"{valor:,.0f} {unidad}"
    resto = unidad[3:]
    if abs(valor) >= 1_000_000:
        return f"${valor / 1_000_000:,.1f} millones MXN{resto}".replace(".0 millones", " millones")
    return f"${valor:,.0f} MXN{resto}"


def _propiedades_destacadas(catalogo: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    vistas, lista = set(), []
    for g in catalogo:
        if g["tipo"] != "propiedades":
            continue
        for p in g["puntos"]:
            clave = p.get("url") or p.get("titulo")
            if clave and clave not in vistas:
                vistas.add(clave)
                lista.append(p)
    return lista[:15]


async def generar_informe(thread_id: str, usuario: Optional[str] = None) -> Dict[str, Any]:
    """Genera el PDF del informe de la conversación `thread_id` y devuelve sus metadatos."""
    import asyncio

    mensajes = await asyncio.to_thread(agente.mensajes_de, thread_id)
    if not any(m["role"] == "assistant" for m in mensajes):
        raise ValueError("La conversación todavía no tiene respuestas para armar un informe.")

    catalogo = _catalogo(mensajes)
    redaccion, pano = await asyncio.gather(
        asyncio.to_thread(_redactar, mensajes, catalogo),
        asyncio.to_thread(panorama),
    )

    # Cada gráfico se usa una sola vez; los que la IA no asignó (salvo listas de propiedades) van en "Anexo".
    usados = set()
    secciones = []
    for s in redaccion.secciones:
        ids = [i for i in s.graficos if 0 <= i < len(catalogo) and i not in usados and catalogo[i]["tipo"] != "propiedades"][:2]
        usados.update(ids)
        secciones.append({"titulo": s.titulo, "parrafos": [p.strip() for p in s.texto.split("\n\n") if p.strip()],
                          "graficos": [catalogo[i] for i in ids]})
    anexo = [g for i, g in enumerate(catalogo) if i not in usados and g["tipo"] != "propiedades"]

    ahora = ahora_mazatlan()
    unicas = next((it["valor"] for it in pano["graficos"][0]["items"] if it["etiqueta"] == "Propiedades analizadas"), None)
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)), autoescape=select_autoescape(["html"]))
    env.filters["valor"] = lambda v, u=None: _formato_valor(v, u)
    html = env.get_template("informe.html").render(
        informe=redaccion,
        secciones=secciones,
        anexo=anexo,
        panorama=pano["graficos"],
        propiedades=_propiedades_destacadas(catalogo),
        fecha=_fecha_larga(ahora),
        propiedades_analizadas=unicas,
        tipo_cambio=TIPO_CAMBIO_USD_MXN,
        logo=LOGO_PATH.resolve().as_uri() if LOGO_PATH.exists() else None,
    )

    INFORMES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"Informe-Mercado-TIBESA-{ahora.strftime('%Y-%m-%d-%H%M%S')}-{_slug(redaccion.titulo)[:30]}.pdf"
    pdf_path = INFORMES_DIR / filename
    html_path = INFORMES_DIR / f".{filename}.html"
    html_path.write_text(html, encoding="utf-8")
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(html_path.resolve().as_uri(), wait_until="networkidle")
            await page.pdf(
                path=str(pdf_path), format="A4", print_background=True,
                margin={"top": "16mm", "right": "14mm", "bottom": "18mm", "left": "14mm"},
                display_header_footer=True,
                header_template="<span></span>",
                footer_template=(
                    "<div style='width:100%;font-family:Helvetica,Arial,sans-serif;font-size:8px;color:#6b7280;padding:0 14mm;display:flex;justify-content:space-between;'>"
                    "<span>TIBESA Bienes Raíces · Informe de Mercado</span>"
                    "<span>Página <span class='pageNumber'></span> de <span class='totalPages'></span></span></div>"
                ),
            )
            await browser.close()
    finally:
        html_path.unlink(missing_ok=True)

    meta = {
        "filename": filename,
        "titulo": redaccion.titulo,
        "subtitulo": redaccion.subtitulo,
        "usuario": usuario,
        "thread_id": thread_id,
        "preguntas": sum(1 for m in mensajes if m["role"] == "user"),
        "created_at": ahora.isoformat(),
        "size_bytes": pdf_path.stat().st_size,
    }
    (INFORMES_DIR / f"{filename}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return meta


def listar_informes() -> List[Dict[str, Any]]:
    if not INFORMES_DIR.exists():
        return []
    informes = []
    for meta_path in INFORMES_DIR.glob("*.pdf.json"):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (INFORMES_DIR / meta.get("filename", "")).exists():
            informes.append(meta)
    return sorted(informes, key=lambda m: m.get("created_at", ""), reverse=True)


def ruta_informe(filename: str) -> Optional[Path]:
    if "/" in filename or "\\" in filename or ".." in filename or not filename.endswith(".pdf"):
        return None
    ruta = INFORMES_DIR / filename
    return ruta if ruta.exists() else None
