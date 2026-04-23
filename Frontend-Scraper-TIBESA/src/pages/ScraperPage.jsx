import { useState, useRef } from 'react'
import { Building2, Sparkles, Play, Loader2, CheckCircle2, Globe, XCircle } from 'lucide-react'
import PropertyCard from '../components/PropertyCard'
import ChatPanel from '../components/ChatPanel'
import SummaryPanel from '../components/SummaryPanel'

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

const API_BASE = 'http://localhost:8000'

export default function ScraperPage() {
  const [status, setStatus] = useState('idle') // idle | extracting | scraping | done | error
  const [activeSite, setActiveSite] = useState(null)
  const [progress, setProgress] = useState({ current: 0, total: 0, percent: 0 })
  const [properties, setProperties] = useState([])
  const [phaseMessage, setPhaseMessage] = useState('')
  const [stats, setStats] = useState(null)
  const eventSourceRef = useRef(null)

  const handleStart = (siteId) => {
    const site = SITES.find(s => s.id === siteId)
    if (!site || site.disabled) return

    // Reset state
    setStatus('extracting')
    setActiveSite(siteId)
    setProperties([])
    setProgress({ current: 0, total: 0, percent: 0 })
    setStats(null)
    setPhaseMessage(`Conectando a ${site.name}...`)

    // Open SSE connection
    const es = new EventSource(`${API_BASE}/api/scrape/stream/${siteId}`)
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

    es.addEventListener('done', (e) => {
      const data = JSON.parse(e.data)
      setStatus('done')
      setStats(data)
      es.close()
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

              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">
                  {site.totalProperties ? `~${site.totalProperties} propiedades` : 'Próximamente'}
                </span>
                {!site.disabled && (
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
                      <><Play className="w-4 h-4" /> Iniciar Scraping</>
                    )}
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Chat with AI - above progress bar */}
      {properties.length > 0 && (
        <ChatPanel properties={properties} />
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
            Propiedades Scrapeadas
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
