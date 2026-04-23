"""
Analyzer: carga JSONs scrapeados, clasifica por zona y calcula estadísticas
(medias de precio, precio/m² terreno, precio/m² construcción) por zona.

Esto es el núcleo del pedido del cliente TIBESA:
  "sacar la media de X zona tanto valor de terreno y construcción
   y que nos arroje la media de lo que analizó de X o Y propiedades"
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import Optional

# ========================================
# Mapping de ubicaciones → zona estratégica
# ========================================

ZONAS_KEYWORDS: dict[str, list[str]] = {
    "Turística": [
        "cerritos", "marina", "marina mazatlan", "sábalo", "sabalo",
        "zona dorada", "el cid", "playa", "gaviotas", "el dorado",
        "rincón de las gaviotas", "rincon de las gaviotas", "telleria",
        "altomare", "pacifika", "pacífika", "club real", "maralto",
    ],
    "Norte": [
        "nuevo mazatlán", "nuevo mazatlan", "real del valle", "venados",
        "la foresta", "santa fe", "el toreo", "lomas del sol",
        "real pacifico", "real pacífico", "stella del mar",
        "sonterra", "torre barak", "valles del ejido", "brisas del vigia",
        "brisas del vigía", "la escopama", "vigía", "vigia",
    ],
    "Centro": [
        "centro", "centro histórico", "centro historico", "olas altas",
        "flamingos", "malecón", "malecon", "playa norte", "los pinos",
        "palos prietos", "juárez", "juarez", "plaza reforma",
    ],
    "Periferia": [
        "villa unión", "villa union", "el venadillo", "siqueros",
        "el quelite", "rural", "carretera", "libramiento",
        "avenidas principales",
    ],
}

ZONA_COLORES: dict[str, str] = {
    "Turística": "#E63946",   # rojo — alta demanda
    "Norte": "#F4A261",        # naranja/amber — crecimiento
    "Centro": "#2A9D8F",       # verde azulado — uso mixto
    "Periferia": "#264653",    # azul oscuro — entrada mercado
    "Sin clasificar": "#9E9E9E",
}


def clasificar_zona(ubicacion: str, zona_llm: Optional[str] = None,
                    colonia_llm: Optional[str] = None) -> str:
    """Clasifica una propiedad en una de las 4 zonas estratégicas."""
    textos = [t.lower() for t in (ubicacion, zona_llm, colonia_llm) if t]
    texto_completo = " ".join(textos)

    for zona, keywords in ZONAS_KEYWORDS.items():
        for kw in keywords:
            if kw in texto_completo:
                return zona

    return "Sin clasificar"


# ========================================
# Extracción normalizada de campos
# ========================================

def _parse_m2(value) -> Optional[float]:
    """Intenta sacar un número en m² de cualquier formato."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    if isinstance(value, str):
        # "550 m²" → 550, "123.0 m²" → 123.0
        match = re.search(r"(\d+(?:\.\d+)?)", value.replace(",", ""))
        if match:
            val = float(match.group(1))
            return val if val > 0 else None
    if isinstance(value, dict):
        # Paraíso Dorado: {"valor": 550, "valor_m2": 550, "unidad": "m2"}
        for key in ("valor_m2", "metros_cuadrados", "superficie_m2", "valor"):
            if key in value:
                return _parse_m2(value[key])
    return None


def _extraer_terreno_m2(prop: dict) -> Optional[float]:
    """Busca m² de terreno en varias rutas posibles del JSON."""
    # Prioridad: analisis_llm > terreno (raíz)
    llm = prop.get("analisis_llm") or {}
    if llm:
        t = llm.get("terreno", {})
        if isinstance(t, dict):
            v = _parse_m2(t.get("metros_cuadrados"))
            if v:
                return v

    t_raiz = prop.get("terreno")
    if isinstance(t_raiz, dict):
        # Lamudi: {"superficie": "219.0 m²", "superficie_m2": 219.0}
        v = _parse_m2(t_raiz.get("superficie_m2"))
        if v:
            return v
        v = _parse_m2(t_raiz.get("superficie"))
        if v:
            return v

    ficha = prop.get("ficha_tecnica") or {}
    v = _parse_m2(ficha.get("superficie_m2"))
    if v:
        return v

    return None


def _extraer_construccion_m2(prop: dict) -> Optional[float]:
    """Busca m² de construcción (usualmente solo en analisis_llm)."""
    llm = prop.get("analisis_llm") or {}
    if llm:
        c = llm.get("construccion", {})
        if isinstance(c, dict):
            v = _parse_m2(c.get("metros_cuadrados"))
            if v:
                return v
    return None


def _extraer_precio(prop: dict) -> Optional[float]:
    pn = prop.get("precio_normalizado") or {}
    p = pn.get("precio_numerico")
    if isinstance(p, (int, float)) and p > 0:
        return float(p)
    return None


def _extraer_primera_imagen(prop: dict) -> Optional[str]:
    imgs = prop.get("imagenes_descargadas") or []
    if imgs:
        return imgs[0]
    return None


def _extraer_zona_llm(prop: dict) -> tuple[Optional[str], Optional[str]]:
    llm = prop.get("analisis_llm") or {}
    uv = llm.get("ubicacion_ventajas") or {}
    return uv.get("zona"), uv.get("colonia")


# ========================================
# Carga y normalización
# ========================================

def cargar_propiedades(json_dir: Path) -> list[dict]:
    """Carga todos los JSONs válidos y normaliza campos clave."""
    propiedades = []
    for json_file in sorted(json_dir.glob("*.json")):
        if json_file.name.startswith("debug_"):
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                prop = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        precio = _extraer_precio(prop)
        if not precio:
            continue  # sin precio no sirve para stats

        terreno_m2 = _extraer_terreno_m2(prop)
        construccion_m2 = _extraer_construccion_m2(prop)
        zona_llm, colonia_llm = _extraer_zona_llm(prop)
        zona = clasificar_zona(
            prop.get("ubicacion", ""), zona_llm, colonia_llm
        )

        propiedades.append({
            "id": prop.get("property_id") or json_file.stem,
            "titulo": prop.get("titulo", "Sin título"),
            "ubicacion": prop.get("ubicacion", ""),
            "tipo_propiedad": prop.get("tipo_propiedad", "N/A"),
            "precio": precio,
            "terreno_m2": terreno_m2,
            "construccion_m2": construccion_m2,
            "precio_m2_terreno": (precio / terreno_m2) if terreno_m2 else None,
            "precio_m2_construccion": (precio / construccion_m2) if construccion_m2 else None,
            "zona": zona,
            "imagen": _extraer_primera_imagen(prop),
            "url": prop.get("url", ""),
            "sitio": prop.get("site", prop.get("empresa", "")),
        })

    return propiedades


# ========================================
# Estadísticas agregadas
# ========================================

def _stats_numerica(valores: list[float]) -> dict:
    valores = [v for v in valores if v is not None and v > 0]
    if not valores:
        return {"count": 0, "media": None, "mediana": None, "min": None, "max": None}
    return {
        "count": len(valores),
        "media": round(statistics.mean(valores), 2),
        "mediana": round(statistics.median(valores), 2),
        "min": round(min(valores), 2),
        "max": round(max(valores), 2),
    }


def estadisticas_por_zona(propiedades: list[dict]) -> dict[str, dict]:
    """
    Calcula, por zona, las medias y rangos que pide el cliente:
    - Media de precio
    - Media de precio/m² terreno
    - Media de precio/m² construcción
    - Conteo de propiedades
    """
    resultado: dict[str, dict] = {}
    zonas = set(p["zona"] for p in propiedades)

    for zona in zonas:
        props = [p for p in propiedades if p["zona"] == zona]

        precios = [p["precio"] for p in props]
        precio_m2_terreno = [p["precio_m2_terreno"] for p in props if p["precio_m2_terreno"]]
        precio_m2_const = [p["precio_m2_construccion"] for p in props if p["precio_m2_construccion"]]
        terreno_m2 = [p["terreno_m2"] for p in props if p["terreno_m2"]]
        construccion_m2 = [p["construccion_m2"] for p in props if p["construccion_m2"]]

        # Distribución por tipo de propiedad
        tipos = {}
        for p in props:
            tipo = (p["tipo_propiedad"] or "N/A").lower()
            tipos[tipo] = tipos.get(tipo, 0) + 1

        resultado[zona] = {
            "zona": zona,
            "color": ZONA_COLORES.get(zona, "#999"),
            "count": len(props),
            "precio": _stats_numerica(precios),
            "precio_m2_terreno": _stats_numerica(precio_m2_terreno),
            "precio_m2_construccion": _stats_numerica(precio_m2_const),
            "terreno_m2": _stats_numerica(terreno_m2),
            "construccion_m2": _stats_numerica(construccion_m2),
            "tipos_propiedad": tipos,
            "ejemplos": [
                {
                    "titulo": p["titulo"],
                    "ubicacion": p["ubicacion"],
                    "precio": p["precio"],
                    "imagen": p["imagen"],
                    "url": p["url"],
                }
                for p in sorted(props, key=lambda x: x["precio"], reverse=True)[:3]
            ],
        }

    return resultado


def resumen_global(propiedades: list[dict]) -> dict:
    """Stats agregados de todo el dataset (slide 2 storytelling, etc.)."""
    precios = [p["precio"] for p in propiedades]
    precio_m2_terreno = [p["precio_m2_terreno"] for p in propiedades if p["precio_m2_terreno"]]
    precio_m2_const = [p["precio_m2_construccion"] for p in propiedades if p["precio_m2_construccion"]]

    sitios = {}
    for p in propiedades:
        sitios[p["sitio"]] = sitios.get(p["sitio"], 0) + 1

    tipos = {}
    for p in propiedades:
        tipo = (p["tipo_propiedad"] or "N/A").lower()
        tipos[tipo] = tipos.get(tipo, 0) + 1

    return {
        "total_propiedades": len(propiedades),
        "precio": _stats_numerica(precios),
        "precio_m2_terreno": _stats_numerica(precio_m2_terreno),
        "precio_m2_construccion": _stats_numerica(precio_m2_const),
        "sitios": sitios,
        "tipos_propiedad": tipos,
    }


# ========================================
# API pública
# ========================================

def analizar_mercado(json_dir: Path | str = "data/json") -> dict:
    """
    Punto de entrada principal. Carga toda la data scrapeada y devuelve
    el dataset analizado listo para alimentar los templates del brochure.
    """
    json_dir = Path(json_dir)
    propiedades = cargar_propiedades(json_dir)

    return {
        "propiedades": propiedades,
        "resumen": resumen_global(propiedades),
        "por_zona": estadisticas_por_zona(propiedades),
        "zonas_colores": ZONA_COLORES,
    }


if __name__ == "__main__":
    # Debug rápido: python -m brochure.analyzer
    import sys
    data = analizar_mercado()
    print(f"\n{'='*60}")
    print(f"Total propiedades válidas: {data['resumen']['total_propiedades']}")
    print(f"Precio promedio: ${data['resumen']['precio']['media']:,.0f} MXN")
    print(f"\n{'='*60}")
    print("POR ZONA:")
    for zona, stats in data["por_zona"].items():
        print(f"\n  🏘️  {zona} ({stats['count']} propiedades)")
        if stats["precio"]["media"]:
            print(f"     Precio medio: ${stats['precio']['media']:,.0f}")
        if stats["precio_m2_terreno"]["media"]:
            print(f"     $/m² terreno: ${stats['precio_m2_terreno']['media']:,.0f}")
        if stats["precio_m2_construccion"]["media"]:
            print(f"     $/m² construcción: ${stats['precio_m2_construccion']['media']:,.0f}")
