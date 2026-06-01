# Snippet SQL — Tabla `tibesa_web_propiedades`

Tabla única para persistir las propiedades scrapeadas de los 4 portales (Paraíso Dorado,
Lamudi, Mitula, RE/MAX Sunset Eagle).

**Diseño:** columnas fijas solo para los campos universales y consultables; toda la estructura
propia de cada web se guarda **íntegra** en el campo `datos` (JSONB) → cero pérdida de datos
aunque cada scraper devuelva una forma distinta.

> Pegar en: Supabase → SQL Editor → New query → Run.

---

## 1. Crear la tabla

```sql
-- =========================================================
-- Tabla: tibesa_web_propiedades
-- Propiedades scrapeadas de los portales inmobiliarios web.
-- =========================================================
create table if not exists public.tibesa_web_propiedades (
    -- Identidad
    id              uuid        primary key default gen_random_uuid(),
    fuente          text        not null,          -- 'paraiso_dorado' | 'lamudi' | 'mitula' | 'remax_sunset_eagle'
    property_id     text        not null,          -- id propio de la propiedad en su portal

    -- Campos universales (para filtrar / consultar / promediar rápido)
    titulo          text,
    precio          text,                           -- precio tal cual viene (ej. "2,500,000 MXN")
    precio_num      numeric,                        -- precio normalizado para ordenar/promediar (opcional)
    moneda          text,                           -- 'MXN' | 'USD'
    ubicacion       text,
    tipo_propiedad  text,                           -- casa, departamento, terreno, etc.
    zona            text,
    url             text,
    imagen_principal text,                          -- URL de la imagen principal (Storage o portal)

    -- Payload completo del scraper, con la forma propia de cada web (SIN pérdida)
    datos           jsonb       not null default '{}'::jsonb,

    -- Metadata de frescura
    scraped_at      timestamptz not null default now(),  -- cuándo se scrapeó esta propiedad
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now(),

    -- Una propiedad es única por (portal + su id). Permite UPSERT al re-scrapear.
    constraint tibesa_web_propiedades_fuente_propid_key unique (fuente, property_id)
);
```

## 2. Índices

```sql
-- Filtrar por portal (ej. "solo Paraíso Dorado")
create index if not exists idx_tibesa_web_prop_fuente
    on public.tibesa_web_propiedades (fuente);

-- Saber qué tan frescos están los datos (última actualización por portal)
create index if not exists idx_tibesa_web_prop_scraped_at
    on public.tibesa_web_propiedades (scraped_at desc);

-- Filtros frecuentes del chat
create index if not exists idx_tibesa_web_prop_tipo
    on public.tibesa_web_propiedades (tipo_propiedad);
create index if not exists idx_tibesa_web_prop_zona
    on public.tibesa_web_propiedades (zona);

-- Búsquedas dentro del JSONB (ej. amenidades, características)
create index if not exists idx_tibesa_web_prop_datos_gin
    on public.tibesa_web_propiedades using gin (datos);
```

## 3. Trigger para mantener `updated_at`

```sql
create or replace function public.set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_tibesa_web_prop_updated_at on public.tibesa_web_propiedades;
create trigger trg_tibesa_web_prop_updated_at
    before update on public.tibesa_web_propiedades
    for each row execute function public.set_updated_at();
```

## 4. RLS (Row Level Security)

El backend escribe con la **service_role key** (que ya usa `supabase_client.py`), la cual
**ignora RLS**. Activamos RLS para que nadie más pueda tocar la tabla con la anon key:

```sql
alter table public.tibesa_web_propiedades enable row level security;
-- Sin políticas públicas: solo la service_role (backend) puede leer/escribir.
```

---

## Cómo se usará desde el backend

### Re-scrapear = reemplazar datos de ese portal (UPSERT)

Al volver a scrapear un portal, cada propiedad se inserta o se actualiza por su clave
`(fuente, property_id)` — así los datos viejos quedan reemplazados sin dejar la tabla vacía:

```sql
insert into public.tibesa_web_propiedades
    (fuente, property_id, titulo, precio, ubicacion, tipo_propiedad, zona, url, imagen_principal, datos, scraped_at)
values
    ('paraiso_dorado', :prop_id, :titulo, :precio, :ubicacion, :tipo, :zona, :url, :img, :datos, now())
on conflict (fuente, property_id) do update set
    titulo           = excluded.titulo,
    precio           = excluded.precio,
    ubicacion        = excluded.ubicacion,
    tipo_propiedad   = excluded.tipo_propiedad,
    zona             = excluded.zona,
    url              = excluded.url,
    imagen_principal = excluded.imagen_principal,
    datos            = excluded.datos,
    scraped_at       = now();
```

### Consultar sin scrapear (lo que alimentará al chat)

```sql
-- Todas las propiedades de un portal
select * from public.tibesa_web_propiedades
where fuente = 'paraiso_dorado'
order by scraped_at desc;
```

### Saber la frescura de cada portal (para el aviso "última actualización hace X días")

```sql
select fuente,
       count(*)            as total_propiedades,
       max(scraped_at)     as ultima_actualizacion
from public.tibesa_web_propiedades
group by fuente;
```

---

## Notas

- **Sin pérdida de datos:** lo que hoy se guarda en `data/json/{fuente}_{id}.json` es exactamente
  lo que irá en la columna `datos` (JSONB). Solo cambia *dónde* se guarda.
- `precio_num` y `moneda` son opcionales; si no se normalizan al scrapear, quedan en `null` y el
  chat puede seguir usando `precio` (texto) o el contenido de `datos`.
- Pendiente aparte: las **imágenes** siguen en disco. Si se decide subirlas a Supabase Storage,
  `imagen_principal` y las rutas dentro de `datos` apuntarían a las URLs del bucket.
