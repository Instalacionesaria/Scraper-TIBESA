"""
Generator: orquesta analyzer + llm_writer + map_generator,
renderiza el template Jinja2 y genera el PDF final con Playwright.
"""

from __future__ import annotations

import random
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import async_playwright

from brochure.analyzer import analizar_mercado, ZONA_COLORES
from brochure.llm_writer import BrochureLLMWriter
from brochure.map_generator import generar_mapa_png


BROCHURE_DIR = Path(__file__).parent
TEMPLATES_DIR = BROCHURE_DIR / "templates"
STATIC_DIR = BROCHURE_DIR / "static"
BACKEND_ROOT = BROCHURE_DIR.parent

DATOS_CONTACTO_TIBESA = {
    "telefono": "(669) 916-0020",
    "whatsapp": "+52 669 155 7199",
    "web": "bienesraicestibesa.mx",
    "redes": "facebook.com/bienesraicestibesa",
}

# Unsplash fallbacks (beach / marina / aerial Mazatlán vibe)
UNSPLASH_HERO = "https://images.unsplash.com/photo-1507525428034-b723cf961d3e?w=1920&q=80"
UNSPLASH_STORY = "https://images.unsplash.com/photo-1545558014-8692077e9b5c?w=1400&q=80"
UNSPLASH_FINAL = "https://images.unsplash.com/photo-1519046904884-53103b34b206?w=1920&q=80"


def _pick_hero_image(propiedades: list[dict]) -> str:
    """Elige una imagen atractiva para el hero de la portada."""
    # Preferimos propiedades con imágenes de playa/marina (Turística, precio alto)
    candidates = [
        p for p in propiedades
        if p.get("imagen") and p.get("zona") == "Turística"
    ]
    if candidates:
        candidates.sort(key=lambda p: p.get("precio", 0), reverse=True)
        # Resolvemos path absoluto
        img_rel = candidates[0]["imagen"]
        abs_path = (BACKEND_ROOT / img_rel).resolve()
        if abs_path.exists():
            return str(abs_path)
    return UNSPLASH_HERO


def _pick_story_image(propiedades: list[dict]) -> str:
    """Imagen distinta para slide 2."""
    candidates = [p for p in propiedades if p.get("imagen") and p.get("zona") == "Turística"]
    if len(candidates) > 3:
        chosen = random.choice(candidates[3:10] if len(candidates) > 10 else candidates[3:])
        abs_path = (BACKEND_ROOT / chosen["imagen"]).resolve()
        if abs_path.exists():
            return str(abs_path)
    return UNSPLASH_STORY


def _pick_final_image(propiedades: list[dict]) -> str:
    candidates = [p for p in propiedades if p.get("imagen")]
    if candidates:
        chosen = random.choice(candidates)
        abs_path = (BACKEND_ROOT / chosen["imagen"]).resolve()
        if abs_path.exists():
            return str(abs_path)
    return UNSPLASH_FINAL


def _formatear_rango(stats: dict) -> str:
    """Devuelve '$X,XXX – $XX,XXX' o '$X,XXX' si no hay rango."""
    if not stats or not stats.get("min"):
        return "N/D"
    mn, mx = stats["min"], stats["max"]
    if mx and mx > mn * 1.2:
        return f"${mn:,.0f} – ${mx:,.0f}"
    return f"${stats['media']:,.0f}"


def _construir_slides_zonas(por_zona: dict) -> list[dict]:
    """Construye los slides 5, 6, 7 (top 3 zonas con mejor muestra)."""
    zonas_orden = [
        ("Turística", "DONDE ESTÁ EL DINERO",
         ["Alta demanda en Airbnb", "Cercanía al mar",
          "Plusvalía inmediata", "Concentración de oferta premium"],
         "Flujo de efectivo + plusvalía"),
        ("Norte", "DONDE ESTÁ EL FUTURO",
         ["Expansión urbana", "Precios accesibles",
          "Crecimiento proyectado", "Desarrollos nuevos en pre-venta"],
         "Compra barato hoy, vende caro mañana"),
        ("Centro", "DONDE ESTÁ EL EQUILIBRIO",
         ["Uso mixto", "Mercado estable",
          "Potencial comercial", "Conectividad con toda la ciudad"],
         "Punto medio: renta estable + valor histórico"),
    ]

    slides = []
    slide_num = 5
    for nombre, categoria, bullets, mensaje in zonas_orden:
        stats = por_zona.get(nombre)
        if not stats or stats.get("count", 0) == 0:
            continue

        slides.append({
            "slide_num": slide_num,
            "nombre": nombre,
            "categoria": categoria,
            "color": stats["color"],
            "count": stats["count"],
            "bullets": bullets,
            "mensaje": mensaje,
            "rango_terreno": _formatear_rango(stats["precio_m2_terreno"]),
            "rango_construccion": (
                _formatear_rango(stats["precio_m2_construccion"])
                if stats["precio_m2_construccion"]["count"] > 0 else None
            ),
        })
        slide_num += 1

    return slides


def _construir_comparables(por_zona: dict) -> list[dict]:
    """Slide 8: barras con precio/m² terreno por zona."""
    rows = []
    valores = []
    for zona, stats in por_zona.items():
        if zona == "Sin clasificar" or stats["count"] == 0:
            continue
        v = stats["precio_m2_terreno"]["media"]
        if not v:
            continue
        valores.append(v)
        rows.append({
            "zona": zona,
            "valor": v,
            "count": stats["count"],
        })

    if not valores:
        return []

    max_v = max(valores)
    for r in rows:
        r["porcentaje"] = round((r["valor"] / max_v) * 100, 1)

    rows.sort(key=lambda x: x["valor"], reverse=True)
    return rows


def _construir_tabla_avaluo(por_zona: dict) -> list[dict]:
    """Slide 9: tabla tipo avalúo."""
    ubicaciones_ejemplo = {
        "Turística": "Cerritos, Marina, Sábalo, El Cid",
        "Norte": "Nuevo Mazatlán, Real del Valle",
        "Centro": "Centro Histórico, Olas Altas",
        "Periferia": "Villa Unión, El Venadillo",
    }

    rows = []
    for zona, stats in por_zona.items():
        if zona == "Sin clasificar" or stats["count"] == 0:
            continue

        pt = stats["precio_m2_terreno"]["media"]
        pc = stats["precio_m2_construccion"]["media"]

        rows.append({
            "zona": zona,
            "color": stats["color"],
            "ubicaciones": ubicaciones_ejemplo.get(zona, "Varias"),
            "precio_terreno": f"${pt:,.0f}" if pt else "N/D",
            "precio_construccion": f"${pc:,.0f}" if pc else "N/D",
            "count": stats["count"],
        })

    rows.sort(key=lambda r: r["count"], reverse=True)
    return rows


def _construir_escenario(por_zona: dict) -> dict:
    """Slide 11: escenario de inversión Norte."""
    norte = por_zona.get("Norte", {})
    terreno = norte.get("precio_m2_terreno", {}).get("media") or 6000
    construccion = 15000
    valor_final = terreno + construccion
    margen = valor_final - (terreno + construccion) + 8000  # estimado plusvalía
    return {
        "precio_terreno": terreno,
        "precio_construccion": construccion,
        "valor_final": valor_final + 2000,  # un poco arriba del costo
        "margen": 8000,  # margen conservador
    }


async def generar_brochure(
    json_dir: Path | str = "data/json",
    output_dir: Path | str = "data/brochures",
    filename: Optional[str] = None,
) -> Path:
    """
    Punto de entrada principal.
    Genera el PDF completo y devuelve la ruta al archivo.
    """
    json_dir = Path(json_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("🔍 Analizando data scrapeada...")
    datos = analizar_mercado(json_dir)

    if datos["resumen"]["total_propiedades"] == 0:
        raise RuntimeError("No hay propiedades scrapeadas para generar el brochure.")

    print(f"   → {datos['resumen']['total_propiedades']} propiedades analizadas")

    print("🧠 Generando copy con LLM...")
    writer = BrochureLLMWriter()
    copy = writer.generar_todo(datos)

    print("🗺️  Generando mapa de oportunidad...")
    mapa_path = output_dir / "tmp" / "mapa.png"
    await generar_mapa_png(datos["por_zona"], mapa_path)

    print("🎨 Renderizando template...")
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("brochure.html")

    context = {
        "copy": copy,
        "por_zona": datos["por_zona"],
        "zonas_colores": ZONA_COLORES,
        "resumen": datos["resumen"],
        "slides_zonas": _construir_slides_zonas(datos["por_zona"]),
        "comparables": _construir_comparables(datos["por_zona"]),
        "tabla_avaluo": _construir_tabla_avaluo(datos["por_zona"]),
        "escenario": _construir_escenario(datos["por_zona"]),
        "contacto": DATOS_CONTACTO_TIBESA,
        "fecha_actual": datetime.now().strftime("%B %Y").upper(),
        "static_dir": str(STATIC_DIR.resolve()),
        "hero_image": _pick_hero_image(datos["propiedades"]),
        "story_image": _pick_story_image(datos["propiedades"]),
        "final_image": _pick_final_image(datos["propiedades"]),
        "mapa_image": str(mapa_path.resolve()),
    }

    html = template.render(**context)
    html_temp = output_dir / "tmp" / "brochure.html"
    html_temp.parent.mkdir(parents=True, exist_ok=True)
    html_temp.write_text(html, encoding="utf-8")

    if not filename:
        filename = f"brochure_tibesa_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    pdf_path = output_dir / filename

    print("📄 Renderizando PDF con Playwright...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 720})
        await page.goto(f"file://{html_temp.absolute()}", wait_until="networkidle")
        await page.wait_for_timeout(1500)  # asegurar carga de fonts/imágenes
        await page.pdf(
            path=str(pdf_path),
            width="1280px",
            height="720px",
            print_background=True,
            prefer_css_page_size=False,
            margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
        )
        await browser.close()

    print(f"✅ Brochure generado: {pdf_path}")
    return pdf_path


if __name__ == "__main__":
    import asyncio
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(generar_brochure())
