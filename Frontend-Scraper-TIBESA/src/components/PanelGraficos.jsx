import { useState } from 'react'
import { BarChart3, ExternalLink, LayoutDashboard, Loader2 } from 'lucide-react'

// Panel derecho del Analista de Mercado. Dibuja las especificaciones que manda el
// backend (calculadas por las herramientas, no por la IA): barras, cifras y propiedades.
// Un solo tono (esmeralda) por gráfico: cada gráfico tiene una sola serie.
const COLOR_MARCA = '#059669' // emerald-600
const COLOR_MARCA_HOVER = '#047857' // emerald-700

function formatoValor(valor, unidad) {
  if (valor === null || valor === undefined) return 'Sin datos'
  if (!unidad || unidad === 'propiedades') return Number(valor).toLocaleString('es-MX')
  const esMoneda = unidad.startsWith('MXN')
  if (!esMoneda) return `${Number(valor).toLocaleString('es-MX')} ${unidad}`
  const resto = unidad.slice(3) // '', '/m²', '/ha'
  if (Math.abs(valor) >= 1_000_000) {
    const millones = (valor / 1_000_000).toLocaleString('es-MX', { maximumFractionDigits: 1 })
    return `$${millones} millones MXN${resto}`
  }
  return `$${Math.round(valor).toLocaleString('es-MX')} MXN${resto}`
}

function Tarjeta({ titulo, children, nota }) {
  return (
    <section className="rounded-2xl border border-gray-200 bg-white p-5">
      <h3 className="mb-4 text-base font-semibold text-gray-900">{titulo}</h3>
      {children}
      {nota && <p className="mt-3 text-sm text-gray-500">{nota}</p>}
    </section>
  )
}

// Ranking horizontal: una barra por fila sobre una misma línea base, valor al final.
function GraficoBarras({ g }) {
  const [activa, setActiva] = useState(null)
  const max = Math.max(...g.filas.map((f) => f.valor), 1)
  const pie = [
    g.orden && `Ordenado de ${g.orden}.`,
    g.omitidas ? `${g.omitidas} zonas más no se muestran.` : null,
    g.nota,
  ].filter(Boolean).join(' ')
  return (
    <Tarjeta titulo={g.titulo} nota={pie}>
      <ul className="space-y-2.5" role="list">
        {g.filas.map((f, i) => (
          <li
            key={f.clave || f.etiqueta}
            className="grid grid-cols-[minmax(0,8rem)_minmax(0,1fr)] items-center gap-3 rounded-md px-1 py-0.5 hover:bg-gray-50"
            onMouseEnter={() => setActiva(i)}
            onMouseLeave={() => setActiva(null)}
            title={`${f.etiqueta}: ${formatoValor(f.valor, g.unidad)}${f.detalle ? ` · ${f.detalle}` : ''}`}
          >
            <span className="truncate text-[15px] text-gray-700">{f.etiqueta}</span>
            <span className="flex items-center gap-2">
              <span className="h-4 min-w-[3rem] flex-1">
                <span
                  className="block h-4 rounded-r-[4px] transition-colors"
                  style={{
                    width: `${Math.max(2, (f.valor / max) * 100)}%`,
                    backgroundColor: activa === i ? COLOR_MARCA_HOVER : COLOR_MARCA,
                  }}
                />
              </span>
              <span className="shrink-0 whitespace-nowrap text-right text-[15px] font-medium tabular-nums text-gray-900">
                {formatoValor(f.valor, g.unidad)}
              </span>
            </span>
            {activa === i && f.detalle && (
              <span className="col-start-2 -mt-1 text-sm text-gray-500">{f.detalle}</span>
            )}
          </li>
        ))}
      </ul>
    </Tarjeta>
  )
}

function GraficoCifras({ g }) {
  return (
    <Tarjeta titulo={g.titulo}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {g.items.filter((it) => it.valor !== null && it.valor !== undefined).map((it) => (
          <div key={it.etiqueta} className="rounded-xl bg-gray-50 px-4 py-3">
            <p className="text-sm text-gray-600">{it.etiqueta}</p>
            <p className="mt-1 text-2xl font-bold tabular-nums text-gray-900">{formatoValor(it.valor, it.unidad)}</p>
            {it.nota && <p className="mt-0.5 text-sm text-gray-500">{it.nota}</p>}
          </div>
        ))}
      </div>
    </Tarjeta>
  )
}

function GraficoPropiedades({ g }) {
  // Barras por propiedad: precio por m² si casi todas lo tienen (mejor para comparar terrenos), si no el precio.
  const conM2 = g.puntos.filter((p) => p.precio_m2)
  const usarM2 = conM2.length >= Math.ceil(g.puntos.length * 0.6)
  const filas = (usarM2 ? conM2 : g.puntos.filter((p) => p.precio)).map((p, i) => ({
    etiqueta: `${g.puntos.indexOf(p) + 1}. ${p.m2 ? `${Number(p.m2).toLocaleString('es-MX')} m²` : (p.zona || '')}`.trim(),
    valor: usarM2 ? p.precio_m2 : p.precio,
    detalle: p.titulo,
    clave: `${p.url}-${i}`,
  }))
  const barras = filas.length > 1 && {
    titulo: usarM2 ? 'Precio por m² de cada propiedad' : 'Precio de cada propiedad',
    unidad: usarM2 ? 'MXN/m²' : 'MXN',
    filas,
    nota: 'El número corresponde a la lista de abajo.',
  }
  return (
    <>
      {barras && <GraficoBarras g={barras} />}
      <Tarjeta
        titulo={g.titulo}
        nota={g.coincidencias ? `Se muestran ${g.puntos.length} de ${g.coincidencias} coincidencias.` : null}
      >
        <ol className="space-y-2">
          {g.puntos.map((p, i) => (
            <li key={`${p.url}-${i}`} className="flex items-start justify-between gap-3 border-t border-gray-100 pt-2 text-[15px] first:border-t-0 first:pt-0">
              <span className="min-w-0">
                <span className="block truncate font-medium text-gray-900">{i + 1}. {p.titulo}</span>
                <span className="block text-sm text-gray-600">
                  {formatoValor(p.precio, 'MXN')}
                  {p.m2 ? ` · ${Number(p.m2).toLocaleString('es-MX')} m²` : ''}
                  {p.precio_m2 ? ` · ${formatoValor(p.precio_m2, 'MXN/m²')}` : ''}
                  {' · '}{p.zona} · {p.portal}
                </span>
              </span>
              {p.url && (
                <a
                  href={p.url} target="_blank" rel="noopener noreferrer"
                  className="inline-flex shrink-0 items-center gap-1 text-sm font-medium text-emerald-700 underline hover:text-emerald-900"
                >
                  Ver anuncio <ExternalLink className="h-3.5 w-3.5" />
                </a>
              )}
            </li>
          ))}
        </ol>
      </Tarjeta>
    </>
  )
}

const RENDER = { barras: GraficoBarras, cifras: GraficoCifras, propiedades: GraficoPropiedades }

export default function PanelGraficos({ graficos, modo, cargando, onVerPanorama, onVerRespuesta, hayRespuesta }) {
  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="inline-flex items-center gap-2 text-lg font-semibold text-gray-900">
          {modo === 'panorama'
            ? <><LayoutDashboard className="h-5 w-5 text-emerald-700" /> Panorama del mercado</>
            : <><BarChart3 className="h-5 w-5 text-emerald-700" /> Gráficos de la respuesta</>}
        </h2>
        {modo === 'respuesta' ? (
          <button onClick={onVerPanorama} className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 cursor-pointer">
            Ver panorama general
          </button>
        ) : hayRespuesta ? (
          <button onClick={onVerRespuesta} className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 cursor-pointer">
            Ver gráficos de la respuesta
          </button>
        ) : null}
      </div>
      <div className="flex-1 space-y-4 overflow-y-auto pb-2">
        {cargando ? (
          <div className="inline-flex items-center gap-2 text-base text-gray-600">
            <Loader2 className="h-5 w-5 animate-spin text-emerald-600" /> Preparando gráficos…
          </div>
        ) : graficos?.length ? (
          graficos.map((g, i) => {
            const Componente = RENDER[g.tipo]
            return Componente ? <Componente key={`${g.tipo}-${g.titulo}-${i}`} g={g} /> : null
          })
        ) : (
          <p className="rounded-2xl border border-dashed border-gray-300 bg-white p-5 text-base text-gray-600">
            Esta respuesta no tiene gráficos. Haga una pregunta sobre precios, zonas o propiedades y aquí aparecerán.
          </p>
        )}
      </div>
    </div>
  )
}
