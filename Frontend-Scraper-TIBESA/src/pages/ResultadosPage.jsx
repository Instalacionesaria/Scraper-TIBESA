import { useState, useEffect } from 'react'
import { BarChart3, FileText, Download, Loader2, CheckCircle2, AlertCircle, Sparkles } from 'lucide-react'

const API_BASE = 'http://localhost:8000'

export default function ResultadosPage() {
  const [propertyCount, setPropertyCount] = useState(0)
  const [brochures, setBrochures] = useState([])
  const [generating, setGenerating] = useState(false)
  const [error, setError] = useState(null)
  const [justGenerated, setJustGenerated] = useState(null)

  // Carga inicial
  useEffect(() => {
    fetchStatus()
  }, [])

  async function fetchStatus() {
    try {
      const [propsRes, brochRes] = await Promise.all([
        fetch(`${API_BASE}/api/properties`),
        fetch(`${API_BASE}/api/brochure/list`),
      ])
      if (propsRes.ok) {
        const data = await propsRes.json()
        setPropertyCount(data.count || 0)
      }
      if (brochRes.ok) {
        const data = await brochRes.json()
        setBrochures(data.brochures || [])
      }
    } catch (e) {
      console.error('Error loading status:', e)
    }
  }

  async function handleGenerate() {
    setGenerating(true)
    setError(null)
    setJustGenerated(null)

    try {
      const res = await fetch(`${API_BASE}/api/brochure/generate`, {
        method: 'POST',
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Error desconocido' }))
        throw new Error(err.detail || 'No se pudo generar el brochure')
      }
      const data = await res.json()
      setJustGenerated(data)
      await fetchStatus()
    } catch (e) {
      setError(e.message)
    } finally {
      setGenerating(false)
    }
  }

  function handleDownload(filename) {
    window.open(`${API_BASE}/api/brochure/download/${filename}`, '_blank')
  }

  function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  function formatDate(iso) {
    try {
      return new Date(iso).toLocaleString('es-MX', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
    } catch {
      return iso
    }
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
          <BarChart3 className="w-7 h-7 text-[#2c3e50]" />
          Resultados & Brochure
        </h1>
        <p className="text-gray-500 mt-1">
          Genera un brochure profesional con el análisis completo de las propiedades scrapeadas
        </p>
      </div>

      {/* Sección de generación de brochure */}
      <div className="bg-gradient-to-br from-[#0B2545] to-[#13315C] rounded-2xl p-8 mb-6 text-white shadow-lg">
        <div className="flex items-start justify-between gap-6 flex-wrap">
          <div className="flex-1 min-w-[300px]">
            <div className="flex items-center gap-2 mb-2">
              <Sparkles className="w-5 h-5 text-[#C9A961]" />
              <span className="text-[11px] tracking-[3px] text-[#C9A961] font-bold uppercase">
                Brochure Inmobiliario TIBESA
              </span>
            </div>
            <h2 className="text-2xl font-bold mb-2">
              Reporte de mercado con análisis por zona
            </h2>
            <p className="text-white/70 text-sm leading-relaxed max-w-xl">
              15 slides con medias de valor de terreno y construcción por zona, comparables,
              escenarios de inversión y todo analizado desde las{' '}
              <span className="text-[#D4B97A] font-semibold">{propertyCount} propiedades</span>{' '}
              scrapeadas. Logo TIBESA incluido.
            </p>
          </div>

          <div className="flex flex-col gap-3">
            <button
              onClick={handleGenerate}
              disabled={generating || propertyCount === 0}
              className="flex items-center gap-2 bg-[#C9A961] hover:bg-[#D4B97A] disabled:bg-white/20 disabled:cursor-not-allowed text-[#0B2545] disabled:text-white/50 font-bold px-6 py-3 rounded-lg transition-colors shadow-md whitespace-nowrap"
            >
              {generating ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  Generando brochure…
                </>
              ) : (
                <>
                  <FileText className="w-5 h-5" />
                  Generar Brochure PDF
                </>
              )}
            </button>
            {propertyCount === 0 && (
              <p className="text-xs text-white/60 text-right">
                Scrapea propiedades primero
              </p>
            )}
          </div>
        </div>

        {/* Feedback post-generación */}
        {justGenerated && (
          <div className="mt-6 bg-white/10 border border-[#C9A961]/40 rounded-lg p-4 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-[#C9A961] flex-shrink-0" />
              <div>
                <div className="font-semibold text-sm">{justGenerated.filename}</div>
                <div className="text-xs text-white/60">
                  {formatBytes(justGenerated.size_bytes)} · Generado correctamente
                </div>
              </div>
            </div>
            <button
              onClick={() => handleDownload(justGenerated.filename)}
              className="flex items-center gap-2 bg-white text-[#0B2545] font-semibold px-4 py-2 rounded-md hover:bg-[#F8F3EA] transition-colors text-sm"
            >
              <Download className="w-4 h-4" />
              Descargar
            </button>
          </div>
        )}

        {error && (
          <div className="mt-6 bg-red-500/20 border border-red-400/40 rounded-lg p-4 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-300 flex-shrink-0" />
            <div className="text-sm text-red-100">{error}</div>
          </div>
        )}
      </div>

      {/* Listado de brochures previos */}
      <div className="bg-white border border-gray-200 rounded-xl p-6">
        <h3 className="text-base font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <FileText className="w-4 h-4 text-gray-500" />
          Brochures generados
          <span className="ml-auto text-xs font-normal text-gray-400">
            {brochures.length} {brochures.length === 1 ? 'archivo' : 'archivos'}
          </span>
        </h3>

        {brochures.length === 0 ? (
          <div className="text-center py-8 text-sm text-gray-400">
            Aún no se ha generado ningún brochure
          </div>
        ) : (
          <div className="divide-y divide-gray-100">
            {brochures.map((b) => (
              <div
                key={b.filename}
                className="flex items-center justify-between py-3 hover:bg-gray-50 px-2 -mx-2 rounded transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <div className="w-10 h-10 bg-[#0B2545] rounded-lg flex items-center justify-center flex-shrink-0">
                    <FileText className="w-5 h-5 text-[#C9A961]" />
                  </div>
                  <div className="min-w-0">
                    <div className="font-medium text-sm text-gray-800 truncate">
                      {b.filename}
                    </div>
                    <div className="text-xs text-gray-400">
                      {formatDate(b.created_at)} · {formatBytes(b.size_bytes)}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => handleDownload(b.filename)}
                  className="flex items-center gap-2 bg-gray-100 hover:bg-[#C9A961] hover:text-white text-gray-700 font-medium px-4 py-2 rounded-md transition-colors text-sm flex-shrink-0"
                >
                  <Download className="w-4 h-4" />
                  Descargar
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
