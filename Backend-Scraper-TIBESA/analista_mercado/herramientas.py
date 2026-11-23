"""
Herramientas (tools) del Analista de Mercado.

Todas las cuentas se hacen aquí, en Python, sobre el inventario normalizado de
`datos.py`; el LLM solo decide qué consultar y explica los resultados. Así los
promedios y medianas salen exactos aunque haya miles de propiedades.
"""

import json
import statistics
from collections import Counter
from typing import Any, Dict, List, Literal, Optional

from langchain.tools import tool

from .datos import GRAN_EXTENSION_M2, NOMBRE_PORTAL, TIPO_CAMBIO_USD_MXN, Propiedad, obtener_inventario, sin_acentos


Tipo = Literal["terreno", "casa", "departamento", "comercial", "otro"]
Operacion = Literal["venta", "renta"]
Ciudad = Literal["Mazatlán", "Otra ciudad", "todas"]


def _json(datos: Any) -> str:
    return json.dumps(datos, ensure_ascii=False, separators=(",", ":"))


def _coincide_zona(p: Propiedad, zonas: Optional[str]) -> bool:
    if not zonas:
        return True
    texto = sin_acentos(f"{p.zona} {p.ubicacion}")
    return any(sin_acentos(z) in texto for z in zonas.split(",") if z.strip())


def _filtrar(
    tipo: Optional[str] = None,
    operacion: Optional[str] = "venta",
    zona: Optional[str] = None,
    ciudad: Optional[str] = "Mazatlán",
    precio_min: Optional[float] = None,
    precio_max: Optional[float] = None,
    superficie_min: Optional[float] = None,
    superficie_max: Optional[float] = None,
    recamaras_min: Optional[int] = None,
    portal: Optional[str] = None,
    texto: Optional[str] = None,
    incluir_duplicados: bool = False,
    incluir_grandes_extensiones: bool = False,
) -> List[Propiedad]:
    if superficie_min and superficie_min >= GRAN_EXTENSION_M2:
        incluir_grandes_extensiones = True  # si piden hectáreas, son justamente esas
    res = []
    for p in obtener_inventario():
        if p.duplicado and not incluir_duplicados:
            continue
        if tipo and p.tipo != tipo:
            continue
        if p.gran_extension and not incluir_grandes_extensiones:
            continue
        if operacion and p.operacion != operacion:
            continue
        if ciudad and ciudad != "todas" and p.ciudad != ciudad:
            continue
        if not _coincide_zona(p, zona):
            continue
        if precio_min is not None and (not p.precio_mxn or p.precio_mxn < precio_min):
            continue
        if precio_max is not None and (not p.precio_mxn or p.precio_mxn > precio_max):
            continue
        if superficie_min is not None and (not p.superficie_m2 or p.superficie_m2 < superficie_min):
            continue
        if superficie_max is not None and (not p.superficie_m2 or p.superficie_m2 > superficie_max):
            continue
        if recamaras_min is not None and (not p.recamaras or p.recamaras < recamaras_min):
            continue
        if portal and sin_acentos(portal) not in sin_acentos(f"{p.portal} {NOMBRE_PORTAL.get(p.portal, '')}"):
            continue
        if texto and not all(t in p.texto_busqueda for t in sin_acentos(texto).split()):
            continue
        res.append(p)
    return res


def _stats(valores: List[float]) -> Optional[Dict[str, Any]]:
    valores = sorted(v for v in valores if v)
    if not valores:
        return None
    n = len(valores)
    cuartiles = statistics.quantiles(valores, n=4) if n >= 4 else [valores[0], statistics.median(valores), valores[-1]]
    return {
        "n": n,
        "mediana": round(statistics.median(valores)),
        "promedio": round(statistics.fmean(valores)),
        "rango_tipico": [round(cuartiles[0]), round(cuartiles[2])],  # del 25% al 75%
        "minimo": round(valores[0]),
        "maximo": round(valores[-1]),
    }


def _ficha(p: Propiedad) -> Dict[str, Any]:
    ficha = {
        "titulo": p.titulo[:90],
        "tipo": p.tipo,
        "precio_mxn": p.precio_mxn,
        "precio_publicado": p.precio_texto,
        "precio_m2": p.precio_m2,
        "superficie_m2": p.superficie_m2,
        "zona": p.zona,
        "portal": NOMBRE_PORTAL.get(p.portal, p.portal),
        "url": p.url,
    }
    if p.construccion_m2:
        ficha["construccion_m2"] = p.construccion_m2
    if p.recamaras:
        ficha["recamaras"] = p.recamaras
    if p.banos:
        ficha["banos"] = p.banos
    if p.tambien_en:
        ficha["tambien_publicada_en"] = p.tambien_en
    if p.nota_precio:
        ficha["nota_precio"] = p.nota_precio
    return {k: v for k, v in ficha.items() if v not in (None, "", [])}


@tool
def resumen_inventario() -> str:
    """Panorama general de TODAS las propiedades guardadas: cuántas hay por tipo, operación (venta/renta),
    ciudad y portal, cuántas tienen precio válido, cuántos duplicados se descartaron y la fecha de los datos.
    Úsala para preguntas como "¿cuántas propiedades tenemos?", "¿de qué portales?" o antes de un análisis general."""
    todas = obtener_inventario()
    unicas = [p for p in todas if not p.duplicado]
    fechas = sorted(p.actualizado for p in todas if p.actualizado)
    return _json({
        "total_registros": len(todas),
        "terrenos_de_1_hectarea_o_mas": sum(1 for p in unicas if p.gran_extension),
        "propiedades_unicas": len(unicas),
        "duplicados_descartados": len(todas) - len(unicas),
        "por_ciudad": dict(Counter(p.ciudad for p in unicas)),
        "por_operacion": dict(Counter(p.operacion for p in unicas)),
        "por_tipo_venta_mazatlan": dict(Counter(p.tipo for p in unicas if p.operacion == "venta" and p.ciudad == "Mazatlán")),
        "por_portal": {NOMBRE_PORTAL.get(k, k): v for k, v in Counter(p.portal for p in unicas).most_common()},
        "sin_precio_valido": sum(1 for p in unicas if not p.precio_mxn),
        "datos_desde": fechas[0][:10] if fechas else None,
        "datos_hasta": fechas[-1][:10] if fechas else None,
        "tipo_cambio_usado": f"1 USD = {TIPO_CAMBIO_USD_MXN} MXN",
    })


@tool
def listar_zonas(
    tipo: Optional[Tipo] = None,
    operacion: Operacion = "venta",
    ciudad: Ciudad = "Mazatlán",
    min_propiedades: int = 3,
) -> str:
    """Lista las zonas/colonias que existen en los datos con cuántas propiedades tiene cada una.
    Úsala cuando el usuario menciona una zona y no estás seguro de cómo aparece escrita en los datos,
    o cuando pregunta "¿qué zonas hay?" / "¿dónde hay más terrenos?"."""
    props = _filtrar(tipo=tipo, operacion=operacion, ciudad=ciudad)
    conteo = Counter(p.zona for p in props)
    return _json({
        "total_propiedades": len(props),
        "zonas": [{"zona": z, "propiedades": n} for z, n in conteo.most_common() if n >= min_propiedades][:60],
    })


@tool
def estadisticas_mercado(
    tipo: Optional[Tipo] = None,
    operacion: Operacion = "venta",
    zona: Optional[str] = None,
    ciudad: Ciudad = "Mazatlán",
    agrupar_por: Optional[Literal["zona", "tipo", "portal", "recamaras"]] = None,
    precio_min: Optional[float] = None,
    precio_max: Optional[float] = None,
    superficie_min: Optional[float] = None,
    superficie_max: Optional[float] = None,
    recamaras_min: Optional[int] = None,
    min_propiedades: int = 3,
    incluir_grandes_extensiones: bool = False,
) -> str:
    """Calcula estadísticas de precios (en MXN) sobre todas las propiedades que cumplen los filtros:
    mediana, promedio, rango típico (25%-75%), mínimo y máximo del PRECIO TOTAL y del PRECIO POR m².
    - zona: texto a buscar en la zona/ubicación; para COMPARAR varias zonas sepáralas con comas
      (p. ej. "Cerritos, Marina, El Cid") y usa agrupar_por="zona".
    - agrupar_por: "zona" para ranking por zona, "tipo", "portal" o "recamaras". Sin agrupar devuelve un solo bloque.
    - min_propiedades: grupos con menos propiedades se omiten (poco representativos).
    - incluir_grandes_extensiones: por defecto se EXCLUYEN terrenos de 1 hectárea o más (ranchos, terrenos rústicos,
      macrolotes para desarrollo), porque su precio por m² es de otro mercado. Ponlo en true solo si el usuario
      pregunta por hectáreas, ranchos, terrenos grandes o para desarrollar.
    Úsala para "¿cuánto cuesta el m² en X?", "¿qué zona es más barata?", "precio promedio de casas", etc."""
    props = _filtrar(tipo=tipo, operacion=operacion, zona=zona, ciudad=ciudad, precio_min=precio_min,
                     precio_max=precio_max, superficie_min=superficie_min, superficie_max=superficie_max,
                     recamaras_min=recamaras_min, incluir_grandes_extensiones=incluir_grandes_extensiones)
    con_precio = [p for p in props if p.precio_mxn]
    if superficie_min and superficie_min >= GRAN_EXTENSION_M2:
        incluir_grandes_extensiones = True

    def bloque(grupo: List[Propiedad]) -> Dict[str, Any]:
        res = {
            "propiedades": len(grupo),
            "precio_total_mxn": _stats([p.precio_mxn for p in grupo]),
            "precio_m2_mxn": _stats([p.precio_m2 for p in grupo if p.precio_m2]),
            "superficie_m2": _stats([p.superficie_m2 for p in grupo if p.superficie_m2]),
        }
        if incluir_grandes_extensiones:
            # Ya calculado para no depender de que el modelo multiplique bien.
            res["precio_hectarea_mxn"] = _stats([p.precio_m2 * 10000 for p in grupo if p.precio_m2])
            res["superficie_hectareas"] = _stats([p.superficie_m2 / 10000 for p in grupo if p.superficie_m2])
        return res

    salida: Dict[str, Any] = {
        "filtros": {k: v for k, v in dict(tipo=tipo, operacion=operacion, zona=zona, ciudad=ciudad,
                    precio_min=precio_min, precio_max=precio_max, superficie_min=superficie_min,
                    superficie_max=superficie_max, recamaras_min=recamaras_min).items() if v is not None},
        "propiedades_encontradas": len(props),
        "con_precio_valido": len(con_precio),
    }
    if not agrupar_por:
        salida["resultado"] = bloque(con_precio)
        return _json(salida)

    grupos: Dict[str, List[Propiedad]] = {}
    for p in con_precio:
        if agrupar_por == "zona":
            clave = p.zona
        elif agrupar_por == "tipo":
            clave = p.tipo
        elif agrupar_por == "portal":
            clave = NOMBRE_PORTAL.get(p.portal, p.portal)
        else:
            clave = f"{p.recamaras} recámaras" if p.recamaras else "sin dato"
        grupos.setdefault(clave, []).append(p)

    filas = [{"grupo": k, **bloque(v)} for k, v in grupos.items() if len(v) >= min_propiedades]
    filas.sort(key=lambda f: -f["propiedades"])
    salida["grupos"] = filas[:30]
    salida["grupos_omitidos_por_pocos_datos"] = sum(1 for v in grupos.values() if len(v) < min_propiedades)
    return _json(salida)


@tool
def buscar_propiedades(
    tipo: Optional[Tipo] = None,
    operacion: Operacion = "venta",
    zona: Optional[str] = None,
    ciudad: Ciudad = "Mazatlán",
    texto: Optional[str] = None,
    precio_min: Optional[float] = None,
    precio_max: Optional[float] = None,
    superficie_min: Optional[float] = None,
    superficie_max: Optional[float] = None,
    recamaras_min: Optional[int] = None,
    portal: Optional[str] = None,
    incluir_grandes_extensiones: bool = False,
    ordenar_por: Literal["precio_asc", "precio_desc", "precio_m2_asc", "precio_m2_desc", "superficie_desc"] = "precio_asc",
    limite: int = 10,
) -> str:
    """Busca propiedades concretas y devuelve su ficha (título, precio, m², precio por m², zona, portal y enlace).
    - texto: palabras que deben aparecer en título/zona/ubicación (p. ej. "frente al mar", "alberca").
    - ordenar_por: "precio_asc" (más baratas), "precio_m2_asc" (mejor precio por m², útil para oportunidades), etc.
    - limite: cuántas devolver (máx. 25).
    - incluir_grandes_extensiones: por defecto se EXCLUYEN terrenos de 1 hectárea o más (ranchos, terrenos rústicos,
      macrolotes para desarrollo), porque su precio por m² es de otro mercado. Ponlo en true solo si el usuario
      pregunta por hectáreas, ranchos, terrenos grandes o para desarrollar.
    Úsala para "muéstrame casas en X", "terrenos de más de 1,000 m²", "las más baratas", "oportunidades"."""
    props = _filtrar(tipo=tipo, operacion=operacion, zona=zona, ciudad=ciudad, texto=texto, precio_min=precio_min,
                     precio_max=precio_max, superficie_min=superficie_min, superficie_max=superficie_max,
                     recamaras_min=recamaras_min, portal=portal,
                     incluir_grandes_extensiones=incluir_grandes_extensiones)
    campo, reverso = {
        "precio_asc": ("precio_mxn", False), "precio_desc": ("precio_mxn", True),
        "precio_m2_asc": ("precio_m2", False), "precio_m2_desc": ("precio_m2", True),
        "superficie_desc": ("superficie_m2", True),
    }[ordenar_por]
    con_valor = [p for p in props if getattr(p, campo)]
    con_valor.sort(key=lambda p: getattr(p, campo), reverse=reverso)
    limite = max(1, min(25, limite))
    return _json({
        "coincidencias": len(props),
        "con_dato_para_ordenar": len(con_valor),
        "mostrando": min(limite, len(con_valor)),
        "propiedades": [_ficha(p) for p in con_valor[:limite]],
    })


HERRAMIENTAS = [resumen_inventario, listar_zonas, estadisticas_mercado, buscar_propiedades]
