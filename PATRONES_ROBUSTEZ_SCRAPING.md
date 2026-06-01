# 🛡️ Patrones de robustez y velocidad para scrapers

Playbook reutilizable de las medidas que implementamos en este proyecto.
Pensado para **copiar/adaptar a otros scrapers**. Cada patrón explica el *problema*,
la *solución* y un *snippet* genérico.

> Contexto donde nació: scraper de propiedades inmobiliarias (Playwright + LLM
> OpenAI + persistencia en Supabase), con corridas largas (cientos/miles de ítems).

---

## 1. 💾 Guardado incremental (NUNCA perder el progreso)

**Problema:** si guardas todo "al final", cualquier corte (crash, cierre, corte de
luz, sin crédito, bloqueo) a la hora 1.5 = **pierdes todo lo avanzado**.

**Solución:** volcar a la base de datos **cada N ítems** (lotes), no al final.

```python
FLUSH_CADA = 25
buffer, guardadas_total = [], 0

async def _flush():
    global buffer, guardadas_total
    if buffer:
        await guardar_en_db(buffer)   # tu upsert
        guardadas_total += len(buffer)
        buffer = []

# en el loop:
buffer.append(item)
if len(buffer) >= FLUSH_CADA:
    await _flush()
# al terminar (o en finally):
await _flush()
```

---

## 2. 🔁 UPSERT con clave única (no duplicar + permitir reanudar)

**Problema:** al re-scrapear o reintentar tras un corte, no quieres duplicar filas.

**Solución:** guardar con **UPSERT** sobre una clave natural `(fuente, id_del_item)`.
Re-correr reemplaza/ignora lo ya guardado → puedes **reanudar** sin limpiar nada.

- En Postgres/Supabase: `on_conflict=fuente,item_id` + `Prefer: resolution=merge-duplicates`.
- **Ojo:** Postgres falla todo el lote si hay claves duplicadas DENTRO del mismo
  comando (`ON CONFLICT ... cannot affect row a second time`). **Deduplica en memoria
  antes de enviar:**

```python
unicos = {row["item_id"]: row for row in rows}  # conserva la última aparición
rows = list(unicos.values())
```

- Para ítems sin id propio, usa un fallback que no choque (la URL, o un hash), nunca
  un índice numérico que pueda coincidir con un id real.

---

## 3. 🪙 Cortar si se agota la cuota/crédito del LLM (OpenAI u otro)

**Problema:** en una corrida larga con LLM, si se acaba el saldo a mitad, no quieres
seguir gastando tiempo ni perder lo hecho.

**Solución:** detectar el error de cuota y **finalizar limpio guardando lo avanzado**.
Muchos SDKs *no lanzan* la excepción hacia arriba (la envuelven), así que revisa el
texto del error.

```python
def es_error_de_cuota(err: str) -> bool:
    err = str(err).lower()
    return any(k in err for k in (
        'insufficient_quota', 'exceeded your current quota',
        'quota', 'billing', 'insufficient funds', 'payment',
    ))
# OJO: NO incluyas 'rate limit'/'429' a secas → suelen ser transitorios, no falta de saldo.

if es_error_de_cuota(error_del_llm):
    await _flush()           # guarda lo avanzado
    motivo = "sin_credito"
    break                    # termina la corrida
```

---

## 4. 🔌 Cortacircuitos por bloqueo del sitio

**Problema:** con muchos requests (sobre todo en paralelo) el sitio puede bloquearte
(403, captcha, Cloudflare, timeouts). Si no lo detectas, el scraper se queda
"moliendo" cientos de fallos perdiendo horas.

**Solución:** contar **fallos seguidos**; si pasan un umbral, asumir bloqueo, **detener
y guardar**. Reiniciar el contador en cada éxito.

```python
UMBRAL_BLOQUEO = 8
fallos_seguidos = 0

# señal de página bloqueada: vino respuesta pero sin datos clave
def extraccion_vacia(data) -> bool:
    return not (data.get('titulo') or data.get('precio'))

if hubo_error or extraccion_vacia(data):
    fallos_seguidos += 1
    if fallos_seguidos >= UMBRAL_BLOQUEO:
        await _flush()
        motivo = "posible_bloqueo"
        break
else:
    fallos_seguidos = 0
```

**Recuperación:** como guardas con UPSERT (patrón 2), esperas un rato y vuelves a
correr; lo ya guardado no se duplica y completas el resto.

---

## 5. ⚡ Paralelizar SIN más hardware (concurrencia I/O)

**Problema:** procesar ítems uno por uno es lentísimo cuando cada uno **espera** red
(cargar la página + llamada al LLM). El CPU está ocioso casi todo el tiempo.

**Solución:** `asyncio` + un **semáforo** para correr N a la vez. No necesitas más
hardware: aprovechas el tiempo de espera (los servidores ajenos hacen el trabajo).

```python
sem = asyncio.Semaphore(5)   # 5 = punto dulce velocidad / no saturar / RAM
async def worker(item):
    async with sem:
        data = await scrapear(item)
        # el LLM síncrono va en un hilo para no bloquear el event loop:
        data = await asyncio.to_thread(procesar_con_llm, data)
        await cola.put(data)
tasks = [asyncio.create_task(worker(i)) for i in items]
```

- **Reusa UN navegador** para todos (abrir/cerrar uno por ítem cuesta ~2-3 s c/u):
  lanza `browser`/`context` una vez y abre/cierra solo una `page` por ítem.
- **Patrón cola (`asyncio.Queue`)** para emitir resultados a streaming (SSE) conforme
  llegan, ya que en paralelo terminan en desorden.
- Concurrencia alta = más riesgo de bloqueo (patrón 4) y más RAM. Si te bloquean,
  baja a 3 o agrega pausas aleatorias.

**Resultado real medido aquí:** de 39 s/ítem a **6.1 s/ítem (~6.4×)**; una corrida de
1400 ítems pasó de ~12 h a ~2.4 h.

---

## 6. 📄 Paginación robusta (no depender de selectores frágiles)

**Problema:** detectar "página siguiente" por un selector de botón (`a[rel=next]`,
`.pagination__page`...) se rompe cuando el sitio cambia su HTML → el scraper cree que
hay 1 sola página y trae una fracción de los datos sin avisar.

**Solución:** apoyarse en señales robustas:
- Recorrer `?page=N` y **parar cuando una página no aporta ítems nuevos** (dedup por id).
- **Tope de seguridad** de páginas para evitar bucles infinitos.

```python
seen, num_pagina, TOPE = set(), 1, 80
while num_pagina <= TOPE:
    items = await extraer_pagina(num_pagina)
    nuevos = [i for i in items if i['id'] not in seen]
    if not nuevos:
        break                       # fin real del listado
    seen.update(i['id'] for i in nuevos)
    num_pagina += 1
```

---

## 7. ✂️ No hacer trabajo innecesario

**Problema:** descargar imágenes/PDFs/recursos pesados que el caso de uso no necesita
multiplica el tiempo y el almacenamiento.

**Solución:** flag para **omitir** lo que no se usa. (Aquí el cliente solo consulta
texto con la IA → desactivamos la descarga de imágenes y ganamos mucho tiempo.)

```python
def __init__(self, ..., descargar_imagenes: bool = True):
    self.descargar_imagenes = descargar_imagenes
# ...
if self.descargar_imagenes:
    data['imagenes'] = await self._descargar(...)
else:
    data['imagenes'] = []
```

---

## 8. ⏱️ Medir tiempos e historial de corridas

**Problema:** no saber cuánto tarda ni cuándo se corrió por última vez.

**Solución:** tabla/log de corridas con `fuente, total, duracion_segundos,
iniciado_at, finalizado_at`. Permite mostrar "última actualización" y "tiempo
promedio", y diagnosticar lentitud.

```python
inicio = time.monotonic()
# ... corrida ...
registrar_corrida(fuente, total, time.monotonic() - inicio, ...)
```

---

## ✅ Checklist rápido para un scraper nuevo

- [ ] ¿Guardo incremental (cada N) y no solo al final?
- [ ] ¿UPSERT con clave única + dedup en memoria antes de enviar?
- [ ] ¿Detecto y corto si se agota la cuota del LLM?
- [ ] ¿Cortacircuitos por fallos seguidos (bloqueo)?
- [ ] ¿Paralelizo con semáforo + reuso de navegador?
- [ ] ¿Paginación por "0 nuevos" + tope, no por selector frágil?
- [ ] ¿Omito descargas que el caso de uso no necesita?
- [ ] ¿Registro duración/historial de cada corrida?
- [ ] ¿El frontend/usuario se entera del motivo de fin (completado / sin crédito / bloqueo)?
