import { Globe, Play, Loader2, CheckCircle2 } from 'lucide-react'

const statusStyles = {
  idle: 'border-gray-200 bg-white',
  running: 'border-sky-300 bg-sky-50 ring-2 ring-sky-100',
  done: 'border-green-300 bg-green-50',
  error: 'border-red-300 bg-red-50',
}

const statusBadge = {
  idle: null,
  running: (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-sky-700 bg-sky-100 px-2 py-0.5 rounded-full">
      <Loader2 className="w-3 h-3 animate-spin" /> Scrapeando...
    </span>
  ),
  done: (
    <span className="inline-flex items-center gap-1 text-xs font-medium text-green-700 bg-green-100 px-2 py-0.5 rounded-full">
      <CheckCircle2 className="w-3 h-3" /> Completado
    </span>
  ),
  error: (
    <span className="text-xs font-medium text-red-700 bg-red-100 px-2 py-0.5 rounded-full">
      Error
    </span>
  ),
}

export default function SiteCard({ site, onStart }) {
  const status = site.status || 'idle'

  return (
    <div className={`rounded-xl border p-5 transition-all ${statusStyles[status]}`}>
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-3">
          {site.logo ? (
            <img src={site.logo} alt={site.name} className="w-10 h-10 rounded-lg object-contain bg-gray-50 p-1" />
          ) : (
            <div className="w-10 h-10 rounded-lg bg-gray-100 flex items-center justify-center">
              <Globe className="w-5 h-5 text-gray-400" />
            </div>
          )}
          <div>
            <h3 className="font-semibold text-gray-900">{site.name}</h3>
            <p className="text-xs text-gray-500">{site.domain}</p>
          </div>
        </div>
        {statusBadge[status]}
      </div>

      <p className="text-sm text-gray-600 mb-4">{site.description}</p>

      <div className="flex items-center justify-between">
        <div className="text-xs text-gray-400">
          {site.totalProperties ? `~${site.totalProperties} propiedades` : 'Propiedades disponibles'}
        </div>
        <button
          onClick={() => onStart(site.id)}
          disabled={status === 'running'}
          className={`inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
            status === 'running'
              ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
              : 'bg-[#2c3e50] text-white hover:bg-[#34495e] cursor-pointer'
          }`}
        >
          {status === 'running' ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Play className="w-4 h-4" />
          )}
          {status === 'running' ? 'En progreso...' : 'Iniciar Scraping'}
        </button>
      </div>

      {/* Progress bar when running */}
      {status === 'running' && site.progress != null && (
        <div className="mt-4">
          <div className="flex justify-between text-xs text-sky-700 mb-1">
            <span>{site.progressText || 'Procesando...'}</span>
            <span>{site.progress}%</span>
          </div>
          <div className="w-full bg-sky-100 rounded-full h-2">
            <div
              className="bg-sky-500 h-2 rounded-full transition-all duration-500"
              style={{ width: `${site.progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Results summary when done */}
      {status === 'done' && site.results && (
        <div className="mt-4 grid grid-cols-3 gap-2 text-center">
          <div className="bg-green-100 rounded-lg p-2">
            <div className="text-lg font-bold text-green-800">{site.results.total}</div>
            <div className="text-[10px] text-green-600">Total</div>
          </div>
          <div className="bg-green-100 rounded-lg p-2">
            <div className="text-lg font-bold text-green-800">{site.results.success}</div>
            <div className="text-[10px] text-green-600">Exitosas</div>
          </div>
          <div className="bg-green-100 rounded-lg p-2">
            <div className="text-lg font-bold text-green-800">{site.results.withAI}</div>
            <div className="text-[10px] text-green-600">Con IA</div>
          </div>
        </div>
      )}
    </div>
  )
}
