"""
Gráficos del panel derecho del Analista de Mercado.

Convierte los RESULTADOS DE LAS HERRAMIENTAS (no el texto del LLM) en
especificaciones de gráfico que dibuja el frontend. Así los números del gráfico
son exactamente los que calculó Python y coinciden con la tabla de la respuesta.

Tipos de especificación:
- barras:      ranking horizontal de un solo color {titulo, unidad, filas:[{etiqueta, valor, detalle}]}
- cifras:      tarjetas de cifra {titulo, items:[{etiqueta, valor, unidad, nota}]}
- propiedades: puntos precio vs m² + lista {titulo, puntos:[...]}
"""

import json
import statistics
from collections import Counter
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from .datos import NOMBRE_PORTAL, obtener_inventario
from .herramientas import _filtrar

MAX_FILAS = 12
NOMBRE_TIPO = {"terreno": "terrenos", "casa": "casas", "departamento": "departamentos",
               "comercial": "locales y comercios", "otro": "otras propiedades"}


def _cargar(contenido: Any) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(contenido) if isinstance(contenido, str) else None
    except (TypeError, ValueError):
        return None


def _tipo_txt(args: Dict[str, Any]) -> str:
    return NOMBRE_TIPO.get(args.get("tipo") or "", "propiedades")


def _sufijo(args: Dict[str, Any]) -> str:
    partes = []
    if args.get("operacion") == "renta":
        partes.append("en renta")
    if args.get("ciudad") and args.get("ciudad") not in ("Mazatlán", None):
        partes.append("todas las ciudades" if args["ciudad"] == "todas" else args["ciudad"].lower())
    return f" ({', '.join(partes)})" if partes else ""


def _mediana(bloque: Optional[Dict[str, Any]]) -> Optional[float]:
    return bloque.get("mediana") if bloque else None


def _de_estadisticas(args: Dict[str, Any], r: Dict[str, Any]) -> List[Dict[str, Any]]:
    tipo = _tipo_txt(args)
    hectareas = bool(args.get("incluir_grandes_extensiones")) or (args.get("superficie_min") or 0) >= 10000
    grupos = r.get("grupos")

    if grupos:
        # En terrenos manda el precio por m² (o por hectárea); en lo demás, el precio total.
        if args.get("tipo") == "terreno":
            clave, unidad, titulo = ("precio_hectarea_mxn", "MXN/ha", f"Precio típico por hectárea de {tipo}") if hectareas \
                else ("precio_m2_mxn", "MXN/m²", f"Precio típico del m² de {tipo}")
        else:
            clave, unidad, titulo = "precio_total_mxn", "MXN", f"Precio típico de {tipo}"
        por = {"zona": "por zona", "tipo": "por tipo", "portal": "por portal", "recamaras": "por recámaras"}.get(args.get("agrupar_por"), "")
        filas = []
        for g in grupos:
            valor = _mediana(g.get(clave))
            if valor:
                n = (g.get(clave) or {}).get("n", g.get("propiedades"))
                filas.append({"etiqueta": g["grupo"], "valor": valor, "detalle": f"{n} propiedades"})
        filas.sort(key=lambda f: f["valor"])
        specs = []
        if filas:
            specs.append({"tipo": "barras", "titulo": f"{titulo} {por}{_sufijo(args)}".replace("  ", " ").strip(),
                          "unidad": unidad, "orden": "menor a mayor", "filas": filas[:MAX_FILAS],
                          "omitidas": max(0, len(filas) - MAX_FILAS)})
        # Comparación de pocas zonas en casas/deptos: segundo gráfico con el m² (escala distinta → gráfico aparte).
        if args.get("tipo") != "terreno" and 2 <= len(grupos) <= 6:
            filas_m2 = [{"etiqueta": g["grupo"], "valor": _mediana(g.get("precio_m2_mxn")),
                         "detalle": f"{(g.get('precio_m2_mxn') or {}).get('n', 0)} con superficie"}
                        for g in grupos if _mediana(g.get("precio_m2_mxn"))]
            if filas_m2:
                filas_m2.sort(key=lambda f: f["valor"])
                specs.append({"tipo": "barras", "titulo": f"Precio típico por m² de {tipo} {por}".strip(),
                              "unidad": "MXN/m²", "orden": "menor a mayor", "filas": filas_m2})
        return specs

    res = r.get("resultado") or {}
    total, m2, ha = res.get("precio_total_mxn"), res.get("precio_m2_mxn"), res.get("precio_hectarea_mxn")
    items = []
    if hectareas and ha:
        items.append({"etiqueta": "Precio típico por hectárea", "valor": ha["mediana"], "unidad": "MXN/ha",
                      "nota": f"la mitad entre ${ha['rango_tipico'][0]:,.0f} y ${ha['rango_tipico'][1]:,.0f}"})
    elif args.get("tipo") == "terreno" and m2:
        items.append({"etiqueta": "Precio típico por m²", "valor": m2["mediana"], "unidad": "MXN/m²",
                      "nota": f"la mitad entre ${m2['rango_tipico'][0]:,.0f} y ${m2['rango_tipico'][1]:,.0f}"})
    if total:
        items.append({"etiqueta": "Precio típico", "valor": total["mediana"], "unidad": "MXN",
                      "nota": f"la mitad entre ${total['rango_tipico'][0]:,.0f} y ${total['rango_tipico'][1]:,.0f}"})
    if m2 and args.get("tipo") != "terreno":
        items.append({"etiqueta": "Precio típico por m²", "valor": m2["mediana"], "unidad": "MXN/m²", "nota": None})
    items.append({"etiqueta": "Propiedades analizadas", "valor": r.get("con_precio_valido", 0), "unidad": None,
                  "nota": "con precio publicado"})
    zona = f" en {args['zona']}" if args.get("zona") else ""
    return [{"tipo": "cifras", "titulo": f"{tipo.capitalize()}{zona}{_sufijo(args)}", "items": items}] if total or m2 else []


def _de_busqueda(args: Dict[str, Any], r: Dict[str, Any]) -> List[Dict[str, Any]]:
    props = r.get("propiedades") or []
    if not props:
        return []
    puntos = [{
        "titulo": p.get("titulo"), "precio": p.get("precio_mxn"), "m2": p.get("superficie_m2"),
        "precio_m2": p.get("precio_m2"), "zona": p.get("zona"), "portal": p.get("portal"), "url": p.get("url"),
    } for p in props]
    zona = f" en {args['zona']}" if args.get("zona") else ""
    return [{"tipo": "propiedades", "titulo": f"{_tipo_txt(args).capitalize()}{zona}{_sufijo(args)}",
             "coincidencias": r.get("coincidencias"), "puntos": puntos}]


def _de_zonas(args: Dict[str, Any], r: Dict[str, Any]) -> List[Dict[str, Any]]:
    zonas = (r.get("zonas") or [])[:MAX_FILAS]
    if not zonas:
        return []
    filas = [{"etiqueta": z["zona"], "valor": z["propiedades"], "detalle": None} for z in zonas]
    return [{"tipo": "barras", "titulo": f"Zonas con más {_tipo_txt(args)}{_sufijo(args)}", "unidad": "propiedades",
             "orden": "mayor a menor", "filas": filas}]


def _de_resumen(r: Dict[str, Any]) -> List[Dict[str, Any]]:
    por_tipo = r.get("por_tipo_venta_mazatlan") or {}
    filas = sorted(({"etiqueta": NOMBRE_TIPO.get(k, k).capitalize(), "valor": v, "detalle": None}
                    for k, v in por_tipo.items()), key=lambda f: -f["valor"])
    portales = [{"etiqueta": k, "valor": v, "detalle": None} for k, v in (r.get("por_portal") or {}).items()][:MAX_FILAS]
    specs = []
    if filas:
        specs.append({"tipo": "barras", "titulo": "Inventario en venta en Mazatlán por tipo", "unidad": "propiedades",
                      "orden": "mayor a menor", "filas": filas})
    if portales:
        specs.append({"tipo": "barras", "titulo": "Propiedades por portal", "unidad": "propiedades",
                      "orden": "mayor a menor", "filas": portales})
    return specs


CONVERSORES = {
    "estadisticas_mercado": _de_estadisticas,
    "buscar_propiedades": _de_busqueda,
    "listar_zonas": _de_zonas,
}


def graficos_de_turno(mensajes: List[BaseMessage]) -> List[Dict[str, Any]]:
    """Gráficos de un turno (los mensajes entre una pregunta y su respuesta final)."""
    args_por_id: Dict[str, Dict[str, Any]] = {}
    for m in mensajes:
        if isinstance(m, AIMessage):
            for tc in m.tool_calls or []:
                args_por_id[tc["id"]] = {"nombre": tc["name"], "args": tc.get("args") or {}}
    specs: List[Dict[str, Any]] = []
    for m in mensajes:
        if not isinstance(m, ToolMessage):
            continue
        llamada = args_por_id.get(m.tool_call_id) or {"nombre": m.name, "args": {}}
        r = _cargar(m.content)
        if r is None:
            continue
        if llamada["nombre"] == "resumen_inventario":
            specs.extend(_de_resumen(r))
        elif llamada["nombre"] in CONVERSORES:
            specs.extend(CONVERSORES[llamada["nombre"]](llamada["args"], r))
    # Los últimos cálculos suelen ser los que sustentan la respuesta final; máximo 3 gráficos.
    return specs[-3:]


def graficos_por_respuesta(mensajes: List[BaseMessage]) -> List[List[Dict[str, Any]]]:
    """Para cada respuesta final del asistente, los gráficos de su turno (en orden)."""
    resultado, turno = [], []
    for m in mensajes:
        if isinstance(m, HumanMessage):
            turno = []
            continue
        turno.append(m)
        if isinstance(m, AIMessage) and not m.tool_calls:
            resultado.append(graficos_de_turno(turno))
            turno = []
    return resultado


# ---------------------------------------------------------------------------
# Panorama general (panel cuando aún no hay preguntas)
# ---------------------------------------------------------------------------

def panorama() -> Dict[str, Any]:
    venta = _filtrar(operacion="venta", ciudad="Mazatlán")
    casas = [p.precio_mxn for p in venta if p.tipo == "casa" and p.precio_mxn]
    deptos = [p.precio_mxn for p in venta if p.tipo == "departamento" and p.precio_mxn]
    terrenos = [p for p in venta if p.tipo == "terreno" and p.precio_m2]

    por_zona: Dict[str, List[float]] = {}
    for p in terrenos:
        if p.zona != "Sin zona especificada":
            por_zona.setdefault(p.zona, []).append(p.precio_m2)
    filas_zona = sorted(
        ({"etiqueta": z, "valor": round(statistics.median(v)), "detalle": f"{len(v)} terrenos"}
         for z, v in por_zona.items() if len(v) >= 8),
        key=lambda f: f["valor"],
    )
    conteo_tipo = Counter(p.tipo for p in venta)
    unicas = [p for p in obtener_inventario() if not p.duplicado]

    return {"graficos": [
        {"tipo": "cifras", "titulo": "Mercado de Mazatlán en venta", "items": [
            {"etiqueta": "Propiedades analizadas", "valor": len(unicas), "unidad": None,
             "nota": f"de {len({p.portal for p in unicas})} portales, sin duplicados"},
            {"etiqueta": "Precio típico de casa", "valor": round(statistics.median(casas)) if casas else None,
             "unidad": "MXN", "nota": f"{len(casas)} casas"},
            {"etiqueta": "Precio típico de departamento", "valor": round(statistics.median(deptos)) if deptos else None,
             "unidad": "MXN", "nota": f"{len(deptos)} departamentos"},
            {"etiqueta": "Precio típico del m² de terreno",
             "valor": round(statistics.median(p.precio_m2 for p in terrenos)) if terrenos else None,
             "unidad": "MXN/m²", "nota": f"{len(terrenos)} terrenos urbanos"},
        ]},
        {"tipo": "barras", "titulo": "Precio típico del m² de terreno por zona", "unidad": "MXN/m²",
         "orden": "menor a mayor", "filas": filas_zona[:MAX_FILAS],
         "nota": "Zonas con al menos 8 terrenos con superficie publicada."},
        {"tipo": "barras", "titulo": "Inventario en venta por tipo", "unidad": "propiedades", "orden": "mayor a menor",
         "filas": [{"etiqueta": NOMBRE_TIPO.get(t, t).capitalize(), "valor": n, "detalle": None}
                   for t, n in conteo_tipo.most_common()]},
    ]}
