"""
Map Generator: construye el mapa de oportunidad de Mazatlán (slide 4) con:
  - Las 4 zonas estratégicas coloreadas (círculos aproximados)
  - Pins de propiedades reales agrupados por zona
  - Leyenda con colores

Usa Folium para generar HTML y Playwright para capturar PNG.
"""

from __future__ import annotations

from pathlib import Path

import folium
from playwright.async_api import async_playwright

from brochure.analyzer import ZONA_COLORES

# Centros aproximados de cada zona en Mazatlán (lat, lng)
# Basado en ubicaciones típicas del mercado inmobiliario
ZONA_CENTROS: dict[str, tuple[float, float, int]] = {
    # zona: (lat, lng, radio en metros)
    "Turística": (23.2550, -106.4471, 3000),   # Zona Dorada / Cerritos / Marina
    "Norte": (23.3000, -106.4150, 4500),        # Nuevo Mazatlán / Real del Valle
    "Centro": (23.2133, -106.4200, 1800),       # Centro Histórico / Olas Altas
    "Periferia": (23.1700, -106.3700, 5000),    # Villa Unión y alrededores
}

MAZATLAN_CENTER = (23.2494, -106.4111)


def _construir_html_mapa(stats_por_zona: dict) -> str:
    """Genera el HTML del mapa con Folium."""
    m = folium.Map(
        location=MAZATLAN_CENTER,
        zoom_start=12,
        tiles="CartoDB positron",
        control_scale=False,
    )

    # Círculos de zona
    for zona, (lat, lng, radio) in ZONA_CENTROS.items():
        stats = stats_por_zona.get(zona, {})
        count = stats.get("count", 0)
        color = ZONA_COLORES.get(zona, "#999")

        folium.Circle(
            location=(lat, lng),
            radius=radio,
            color=color,
            weight=3,
            fill=True,
            fill_color=color,
            fill_opacity=0.22,
        ).add_to(m)

        # Etiqueta con nombre de zona y conteo
        folium.Marker(
            location=(lat, lng),
            icon=folium.DivIcon(
                html=f"""
                <div style="
                    background: {color};
                    color: white;
                    padding: 6px 12px;
                    border-radius: 20px;
                    font-family: 'Inter', sans-serif;
                    font-weight: 700;
                    font-size: 13px;
                    white-space: nowrap;
                    box-shadow: 0 2px 8px rgba(0,0,0,0.25);
                    text-align: center;
                    border: 2px solid white;
                ">
                    {zona}<br/>
                    <span style="font-size: 10px; font-weight: 400;">{count} propiedades</span>
                </div>
                """,
                icon_size=(140, 50),
                icon_anchor=(70, 25),
            ),
        ).add_to(m)

    return m.get_root().render()


async def generar_mapa_png(
    stats_por_zona: dict,
    output_path: Path,
    width: int = 1200,
    height: int = 800,
) -> Path:
    """
    Genera un PNG del mapa de oportunidad.
    Devuelve la ruta del archivo generado.
    """
    html = _construir_html_mapa(stats_por_zona)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    html_temp = output_path.with_suffix(".html")
    html_temp.write_text(html, encoding="utf-8")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": width, "height": height})
        await page.goto(f"file://{html_temp.absolute()}", wait_until="networkidle")
        # Esperar a que los tiles carguen
        await page.wait_for_timeout(2500)
        await page.screenshot(path=str(output_path), full_page=False)
        await browser.close()

    return output_path


if __name__ == "__main__":
    # Debug: python -m brochure.map_generator
    import asyncio
    from brochure.analyzer import analizar_mercado

    async def main():
        datos = analizar_mercado()
        out = await generar_mapa_png(
            datos["por_zona"],
            Path("data/brochures/tmp/mapa_test.png"),
        )
        print(f"Mapa generado: {out}")

    asyncio.run(main())
