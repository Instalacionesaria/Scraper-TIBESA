"""Test del scraper RE/MAX Sunset Eagle: zona Nuevo Mazatlán (9 propiedades)."""

import asyncio
import json
import sys

from scrapers.remax_sunset_eagle import RemaxSunsetEagleScraper


async def main():
    scraper = RemaxSunsetEagleScraper(
        output_dir="data",
        descargar_imagenes=True,
        max_imagenes_por_propiedad=1,
        concurrencia=4,
    )

    resultado = await scraper.scrape_zona(zona_id=7, guardar=True)

    print(f"\n{'=' * 80}")
    print(f"✅ RESUMEN — {resultado['zona_nombre']}")
    print(f"{'=' * 80}")
    print(f"   Total reportado en sitio: {resultado['total_reportado']}")
    print(f"   Total scrapeadas:         {resultado['total_scrapeadas']}")

    if resultado["propiedades"]:
        muestra = resultado["propiedades"][0]
        print(f"\n📋 Muestra (primera propiedad):")
        for k in [
            "url", "property_id", "titulo", "tipo_operacion", "tipo_propiedad",
            "ubicacion", "codigo", "precio", "precio_numerico", "moneda",
            "terreno", "caracteristicas", "agente",
        ]:
            print(f"   {k}: {muestra.get(k)}")
        if muestra.get("descripcion"):
            d = muestra["descripcion"]
            print(f"   descripcion: {d[:120]}{'...' if len(d) > 120 else ''}")
        print(f"   amenidades ({len(muestra.get('amenidades', []))}): {muestra.get('amenidades', [])[:5]}...")
        print(f"   imagenes_descargadas: {muestra.get('imagenes_descargadas')}")

    return 0 if resultado["total_scrapeadas"] > 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
