# Snippet SQL — Tabla `tibesa_scrapeos_log`

Historial de cada corrida de scraping por portal. Sirve para:
- Calcular la **duración promedio** de scrapear cada web (se muestra en el frontend).
- Guardar la **última duración** y cuántas propiedades trajo cada corrida.
- Tener un historial auditable de cuándo se scrapeó.

> Pegar en: Supabase → SQL Editor → New query → Run and enable RLS.

---

## 1. Crear la tabla

```sql
create table if not exists public.tibesa_scrapeos_log (
    id                  uuid        primary key default gen_random_uuid(),
    fuente              text        not null,     -- paraiso_dorado | lamudi | mitula | remax_sunset_eagle
    total_propiedades   integer     not null default 0,
    duracion_segundos   numeric     not null default 0,   -- cuánto tardó la corrida
    iniciado_at         timestamptz,
    finalizado_at       timestamptz not null default now(),
    created_at          timestamptz not null default now()
);
```

## 2. Índices

```sql
-- Promedio y última corrida por portal
create index if not exists idx_tibesa_scrapeos_fuente_fin
    on public.tibesa_scrapeos_log (fuente, finalizado_at desc);
```

## 3. RLS

```sql
alter table public.tibesa_scrapeos_log enable row level security;
-- Sin políticas públicas: solo la service_role (backend) lee/escribe.
```

---

## Cómo se usa

- **Al terminar un scrapeo**, el backend inserta una fila con la duración medida.
- **El promedio** se calcula sobre las últimas N corridas:
  ```sql
  select fuente,
         avg(duracion_segundos) as duracion_promedio_seg,
         count(*)               as total_corridas
  from public.tibesa_scrapeos_log
  group by fuente;
  ```
