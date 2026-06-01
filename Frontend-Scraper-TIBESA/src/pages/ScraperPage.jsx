import { useState, useRef, useEffect, useCallback } from 'react'
import { Building2, Sparkles, Play, Loader2, CheckCircle2, Globe, XCircle, Database, Clock, Timer } from 'lucide-react'
import PropertyCard from '../components/PropertyCard'
import ChatPanel from '../components/ChatPanel'
import SummaryPanel from '../components/SummaryPanel'

// Convierte un timestamp ISO a texto relativo ("hace 2 días", "hace 3 h").
function tiempoRelativo(iso) {
  if (!iso) return null
  const fecha = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z')
  const segs = Math.floor((Date.now() - fecha.getTime()) / 1000)
  if (segs < 60) return 'hace unos segundos'
  const mins = Math.floor(segs / 60)
  if (mins < 60) return `hace ${mins} min`
  const horas = Math.floor(mins / 60)
  if (horas < 24) return `hace ${horas} h`
  const dias = Math.floor(horas / 24)
  if (dias === 1) return 'hace 1 día'
  return `hace ${dias} días`
}

// Formatea un timestamp ISO como "Domingo 31 de Mayo a las 10:25 horas" (hora local).
const DIAS_SEMANA = ['Domingo', 'Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado']
const MESES = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre']
function fechaLarga(iso) {
  if (!iso) return null
  const d = new Date(iso.endsWith('Z') || iso.includes('+') ? iso : iso + 'Z')
  if (isNaN(d.getTime())) return null
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${DIAS_SEMANA[d.getDay()]} ${d.getDate()} de ${MESES[d.getMonth()]} a las ${hh}:${mm} horas`
}

// Formatea segundos como "3 min 20 s" o "45 s".
function formatDuracion(seg) {
  if (seg == null || isNaN(seg)) return null
  const s = Math.round(seg)
  if (s < 60) return `${s} s`
  const min = Math.floor(s / 60)
  const resto = s % 60
  return resto ? `${min} min ${resto} s` : `${min} min`
}

const SITES = [
  {
    id: 'paraiso_dorado',
    name: 'Paraiso Dorado',
    domain: 'paraisodorado.com.mx',
    description: 'Inmobiliaria líder en Mazatlán. Casas, departamentos, terrenos, locales comerciales y condominios.',
    totalProperties: 72,
  },
  {
    id: 'lamudi',
    name: 'Lamudi',
    domain: 'lamudi.com.mx',
    description: 'Portal inmobiliario con +1,400 propiedades en Mazatlán. Casas, departamentos, terrenos y más.',
    totalProperties: 1445,
  },
  {
    id: 'mitula',
    name: 'Mitula',
    domain: 'casas.mitula.mx',
    description: 'Agregador inmobiliario con ~718 propiedades en venta en Mazatlán. Datos completos desde listado.',
    totalProperties: 718,
  },
  {
    id: 'remax_sunset_eagle',
    name: 'RE/MAX Sunset Eagle',
    domain: 'es.remaxsunseteagle.com',
    description: 'Inmobiliaria con cobertura en 8 zonas de Mazatlán. Selecciona una zona específica o scrapea todas.',
    totalProperties: 422,
    hasZoneSelector: true,
    zones: [
      { id: null, label: 'Todas las zonas', count: 422 },
      { id: 1, label: 'Centro Histórico', count: 56 },
      { id: 2, label: 'Malecón', count: 71 },
      { id: 3, label: 'Zona Dorada / Sábalo', count: 47 },
      { id: 4, label: 'Playa Sur', count: 2 },
      { id: 5, label: 'Marina', count: 49 },
      { id: 6, label: 'Cerritos', count: 64 },
      { id: 7, label: 'Nuevo Mazatlán', count: 9 },
      { id: 8, label: 'Este Mazatlán', count: 61 },
    ],
  },
  {
    id: 'invest_mazatlan',
    name: 'Invest Mazatlán',
    domain: 'investmazatlan.com',
    description: 'Propiedades de inversión en Mazatlán. Desarrollos nuevos, preventa y proyectos exclusivos.',
    totalProperties: null,
    disabled: true,
  },
  {
    id: 'inmuebles24',
    name: 'Inmuebles24',
    domain: 'inmuebles24.com',
    description: 'Portal inmobiliario nacional. Bloqueado por Cloudflare.',
    totalProperties: null,
    disabled: true,
  },
]

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export default function ScraperPage() {
  const [status, setStatus] = useState('idle') // idle | extracting | scraping | done | error
  const [activeSite, setActiveSite] = useState(null)
  const [progress, setProgress] = useState({ current: 0, total: 0, percent: 0 })
  const [properties, setProperties] = useState([])
  const [phaseMessage, setPhaseMessage] = useState('')
  const [stats, setStats] = useState(null)
  const [selectedZones, setSelectedZones] = useState({}) // { siteId: zoneId | null }
  const [estado, setEstado] = useState({}) // { fuente: { total_propiedades, ultima_actualizacion } }
  const [dataSource, setDataSource] = useState(null) // null | 'live' | 'saved'
  const [loadingSaved, setLoadingSaved] = useState(null) // siteId que se está cargando
  const eventSourceRef = useRef(null)

  // Cargar frescura de los datos guardados por portal
  const refreshEstado = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/api/propiedades/estado`)
      const data = await res.json()
      const mapa = {}
      for (const e of data.estado || []) mapa[e.fuente] = e
      setEstado(mapa)
    } catch {
      // backend apagado: no bloqueamos la UI
    }
  }, [])

  useEffect(() => { refreshEstado() }, [refreshEstado])

  // Consultar lo guardado en Supabase SIN volver a scrapear
  const handleConsultarGuardado = async (siteId) => {
    const site = SITES.find(s => s.id === siteId)
    if (!site) return
    setLoadingSaved(siteId)
    try {
      const res = await fetch(`${API_BASE}/api/propiedades?fuente=${siteId}`)
      const data = await res.json()
      setProperties(data.properties || [])
      setActiveSite(siteId)
      setDataSource('saved')
      setStatus('idle')
      setStats(null)
    } catch {
      setPhaseMessage('No se pudieron cargar los datos guardados')
    } finally {
      setLoadingSaved(null)
    }
  }

  const handleStart = (siteId) => {
    const site = SITES.find(s => s.id === siteId)
    if (!site || site.disabled) return

    // Reset state
    setStatus('extracting')
    setActiveSite(siteId)
    setDataSource('live')
    setProperties([])
    setProgress({ current: 0, total: 0, percent: 0 })
    setStats(null)
    setPhaseMessage(`Conectando a ${site.name}...`)

    // Build URL with optional zone query param
    const zoneId = selectedZones[siteId]
    const url = zoneId
      ? `${API_BASE}/api/scrape/stream/${siteId}?zona=${zoneId}`
      : `${API_BASE}/api/scrape/stream/${siteId}`

    // Open SSE connection
    const es = new EventSource(url)
    eventSourceRef.current = es

    es.addEventListener('phase', (e) => {
      const data = JSON.parse(e.data)
      setPhaseMessage(data.message)
      if (data.phase === 'scraping') {
        setStatus('scraping')
        setProgress(p => ({ ...p, total: data.total }))
      }
    })

    es.addEventListener('progress', (e) => {
      const data = JSON.parse(e.data)
      setProgress({ current: data.current, total: data.total, percent: data.percent })
    })

    es.addEventListener('property', (e) => {
      const data = JSON.parse(e.data)
      setProperties(prev => [data, ...prev])
    })

    es.addEventListener('property_error', (e) => {
      const data = JSON.parse(e.data)
      setProperties(prev => [{ ...data, isError: true, titulo: `Error: ${data.error}`, url: data.url }, ...prev])
    })

    es.addEventListener('warning', (e) => {
      try {
        const data = JSON.parse(e.data)
        setPhaseMessage(data.message || 'Aviso')
      } catch { /* ignore */ }
    })

    es.addEventListener('done', (e) => {
      const data = JSON.parse(e.data)
      setStatus('done')
      setStats(data)
      if (data.motivo === 'sin_credito_openai') {
        setPhaseMessage('⚠️ Se agotó el crédito de OpenAI. Se guardó todo lo avanzado hasta aquí.')
      } else if (data.motivo === 'posible_bloqueo') {
        setPhaseMessage('⚠️ El sitio podría habernos bloqueado. Se guardó todo lo avanzado. Intenta de nuevo más tarde.')
      }
      es.close()
      refreshEstado() // los datos se acaban de persistir en Supabase
    })

    es.addEventListener('error', (e) => {
      // SSE spec fires error on close too, ignore if done
      if (status === 'done') return
      try {
        const data = JSON.parse(e.data)
        setPhaseMessage(data.message || 'Error de conexión')
      } catch {
        setPhaseMessage('Conexión perdida con el servidor')
      }
      setStatus('error')
      es.close()
    })

    es.onerror = () => {
      if (eventSourceRef.current?.readyState === EventSource.CLOSED) return
      setStatus('error')
      setPhaseMessage('No se pudo conectar al servidor. Asegúrate de que el backend esté corriendo en localhost:8000')
      es.close()
    }
  }

  const handleStop = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
    }
    setStatus('idle')
    setActiveSite(null)
  }

  const isActive = status !== 'idle'

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
          <Building2 className="w-7 h-7 text-[#2c3e50]" />
          Scraper Inmobiliario
        </h1>
        <p className="text-gray-500 mt-1">
          Selecciona un sitio inmobiliario de Mazatlán para scrapear
        </p>
      </div>

      {/* AI Badge */}
      <div className="mb-6 inline-flex items-center gap-2 bg-violet-50 border border-violet-200 text-violet-700 px-4 py-2 rounded-lg text-sm">
        <Sparkles className="w-4 h-4" />
        Cada propiedad se analiza con <strong>IA (GPT-5 mini)</strong> para extraer tipo, tamaño, zona y características
      </div>

      {/* Sites grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-8">
        {SITES.map(site => {
          const isRunning = activeSite === site.id && (status === 'extracting' || status === 'scraping')
          const isDone = activeSite === site.id && status === 'done'
          const info = estado[site.id]
          const tieneGuardado = info && info.total_propiedades > 0
          const isLoadingSaved = loadingSaved === site.id

          return (
            <div
              key={site.id}
              className={`rounded-xl border p-5 transition-all ${
                isRunning ? 'border-sky-300 bg-sky-50 ring-2 ring-sky-100' :
                isDone ? 'border-green-300 bg-green-50' :
                site.disabled ? 'border-gray-200 bg-gray-50 opacity-60' :
                'border-gray-200 bg-white hover:shadow-sm'
              }`}
            >
              <div className="flex items-start justify-between mb-2">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center">
                    <Globe className="w-5 h-5 text-gray-400" />
                  </div>
                  <div>
                    <h3 className="font-semibold text-gray-900">{site.name}</h3>
                    <p className="text-xs text-gray-500">{site.domain}</p>
                  </div>
                </div>
                {isRunning && (
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-sky-700 bg-sky-100 px-2 py-0.5 rounded-full">
                    <Loader2 className="w-3 h-3 animate-spin" /> Scrapeando...
                  </span>
                )}
                {isDone && (
                  <span className="inline-flex items-center gap-1 text-xs font-medium text-green-700 bg-green-100 px-2 py-0.5 rounded-full">
                    <CheckCircle2 className="w-3 h-3" /> Completado
                  </span>
                )}
              </div>

              <p className="text-sm text-gray-600 mb-3">{site.description}</p>

              {/* Datos guardados en Supabase */}
              {!site.disabled && tieneGuardado && (
                <div className="mb-3 flex items-center gap-2 text-xs bg-gray-50 border border-gray-100 rounded-lg px-3 py-2">
                  <Database className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                  <span className="text-gray-600">
                    <strong className="text-gray-800">{info.total_propiedades}</strong> guardadas
                  </span>
                  {info.ultima_actualizacion && (
                    <span className="inline-flex items-center gap-1 text-gray-400">
                      <Clock className="w-3 h-3" /> {tiempoRelativo(info.ultima_actualizacion)}
                    </span>
                  )}
                </div>
              )}

              {site.hasZoneSelector && !site.disabled && (
                <div className="mb-3">
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Zona a scrapear:
                  </label>
                  <select
                    value={selectedZones[site.id] ?? ''}
                    onChange={(e) => {
                      const v = e.target.value
                      setSelectedZones(prev => ({
                        ...prev,
                        [site.id]: v === '' ? null : Number(v),
                      }))
                    }}
                    disabled={isRunning || (isActive && !isRunning)}
                    className="w-full text-sm rounded-lg border border-gray-300 bg-white px-3 py-2 focus:outline-none focus:ring-2 focus:ring-sky-200 disabled:bg-gray-50 disabled:text-gray-400 cursor-pointer"
                  >
                    {site.zones.map(z => (
                      <option key={z.id ?? 'all'} value={z.id ?? ''}>
                        {z.label} ({z.count} propiedades)
                      </option>
                    ))}
                  </select>
                </div>
              )}

              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">
                  {site.hasZoneSelector
                    ? (() => {
                        const z = site.zones.find(zz => zz.id === (selectedZones[site.id] ?? null))
                        return z ? `~${z.count} propiedades` : `~${site.totalProperties} propiedades`
                      })()
                    : site.totalProperties
                      ? `~${site.totalProperties} propiedades`
                      : 'Próximamente'
                  }
                </span>
                {!site.disabled && (
                  <div className="flex items-center gap-2">
                    {tieneGuardado && !isRunning && (
                      <button
                        onClick={() => handleConsultarGuardado(site.id)}
                        disabled={isActive || isLoadingSaved}
                        title="Cargar lo guardado sin volver a scrapear"
                        className="inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium border border-gray-200 text-gray-700 bg-white hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed transition-colors cursor-pointer"
                      >
                        {isLoadingSaved ? <Loader2 className="w-4 h-4 animate-spin" /> : <Database className="w-4 h-4" />}
                        Consultar guardado
                      </button>
                    )}
                    <button
                      onClick={() => isRunning ? handleStop() : handleStart(site.id)}
                      disabled={isActive && !isRunning}
                      className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
                        isRunning
                          ? 'bg-red-500 text-white hover:bg-red-600'
                          : isActive
                          ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                          : 'bg-[#2c3e50] text-white hover:bg-[#34495e]'
                      }`}
                    >
                      {isRunning ? (
                        <><XCircle className="w-4 h-4" /> Detener</>
                      ) : (
                        <><Play className="w-4 h-4" /> {tieneGuardado ? 'Re-scrapear' : 'Iniciar Scraping'}</>
                      )}
                    </button>
                  </div>
                )}
              </div>

              {/* Fecha del último scrapeo + duración promedio */}
              {!site.disabled && (
                <div className="mt-3 pt-3 border-t border-gray-100 space-y-1.5">
                  <div className="flex items-center gap-1.5 text-xs text-gray-500">
                    <Clock className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                    {info?.ultima_actualizacion ? (
                      <span>
                        Último scrapeo realizado:{' '}
                        <span className="font-medium text-gray-700">{fechaLarga(info.ultima_actualizacion)}</span>
                      </span>
                    ) : (
                      <span className="text-gray-400">Aún no se ha realizado ningún scrapeo</span>
                    )}
                  </div>
                  {info?.duracion_promedio_seg != null && (
                    <div className="flex items-center gap-1.5 text-xs text-gray-500">
                      <Timer className="w-3.5 h-3.5 text-gray-400 shrink-0" />
                      <span>
                        Tiempo promedio de scrapeo:{' '}
                        <span className="font-medium text-gray-700">~{formatDuracion(info.duracion_promedio_seg)}</span>
                        {info.total_corridas > 1 && (
                          <span className="text-gray-400"> (sobre {info.total_corridas} corridas)</span>
                        )}
                      </span>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Banner: datos guardados (consulta sin scrapear) */}
      {dataSource === 'saved' && properties.length > 0 && (
        <div className="mb-4 flex items-center gap-2 bg-emerald-50 border border-emerald-200 text-emerald-800 px-4 py-2.5 rounded-lg text-sm">
          <Database className="w-4 h-4 shrink-0" />
          <span>
            Mostrando <strong>{properties.length}</strong> propiedades guardadas de{' '}
            <strong>{SITES.find(s => s.id === activeSite)?.name}</strong>
            {estado[activeSite]?.ultima_actualizacion && (
              <> · actualizado {tiempoRelativo(estado[activeSite].ultima_actualizacion)}</>
            )}
            . No se volvió a scrapear.
          </span>
        </div>
      )}

      {/* Chat with AI - above progress bar */}
      {properties.length > 0 && (
        <ChatPanel properties={properties} fuente={dataSource === 'saved' ? activeSite : null} />
      )}

      {/* Progress section */}
      {isActive && (
        <div className="mb-6">
          {/* Progress bar */}
          <div className="bg-white border border-gray-200 rounded-xl p-5">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-gray-700">{phaseMessage}</span>
              {status === 'scraping' && (
                <span className="text-sm font-bold text-sky-700">
                  {progress.current} / {progress.total} ({progress.percent}%)
                </span>
              )}
            </div>
            <div className="w-full bg-gray-100 rounded-full h-3">
              <div
                className={`h-3 rounded-full transition-all duration-500 ${
                  status === 'done' ? 'bg-green-500' :
                  status === 'error' ? 'bg-red-500' :
                  status === 'extracting' ? 'bg-sky-400 animate-pulse' :
                  'bg-sky-500'
                }`}
                style={{ width: status === 'extracting' ? '100%' : `${progress.percent}%` }}
              />
            </div>

            {/* Stats when done */}
            {stats && (
              <div className="grid grid-cols-4 gap-3 mt-4">
                <div className="text-center bg-gray-50 rounded-lg p-3">
                  <div className="text-2xl font-bold text-gray-800">{stats.total}</div>
                  <div className="text-xs text-gray-500">Total</div>
                </div>
                <div className="text-center bg-green-50 rounded-lg p-3">
                  <div className="text-2xl font-bold text-green-700">{stats.exitosas}</div>
                  <div className="text-xs text-green-600">Exitosas</div>
                </div>
                <div className="text-center bg-violet-50 rounded-lg p-3">
                  <div className="text-2xl font-bold text-violet-700">{stats.con_ia}</div>
                  <div className="text-xs text-violet-600">Con IA</div>
                </div>
                <div className="text-center bg-red-50 rounded-lg p-3">
                  <div className="text-2xl font-bold text-red-700">{stats.fallidas}</div>
                  <div className="text-xs text-red-600">Fallidas</div>
                </div>
              </div>
            )}
            {stats?.duracion_segundos != null && (
              <div className="mt-3 flex items-center justify-center gap-1.5 text-sm text-gray-500">
                <Timer className="w-4 h-4 text-gray-400" />
                Completado en <span className="font-medium text-gray-700">{formatDuracion(stats.duracion_segundos)}</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Summary panel - below progress bar, shows when done or has properties */}
      {properties.length > 0 && (
        <SummaryPanel properties={properties} />
      )}

      {/* Live properties feed */}
      {properties.length > 0 && (
        <div>
          <h2 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
            {dataSource === 'saved' ? 'Propiedades Guardadas' : 'Propiedades Scrapeadas'}
            <span className="text-sm font-normal text-gray-400">({properties.length})</span>
          </h2>
          <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
            {properties.map((prop, i) => (
              prop.isError ? (
                <div key={i} className="bg-red-50 border border-red-200 rounded-xl p-4 text-sm text-red-600">
                  <span className="font-medium">Error en propiedad #{prop.index}:</span> {prop.error}
                </div>
              ) : (
                <PropertyCard key={i} property={prop} index={prop.index} />
              )
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
