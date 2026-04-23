import { useState } from 'react'
import { Search, Play, Loader2, Send, Database } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

const MAX_ETIQUETA_LEN = 30

export default function BusquedaLeadsPage() {
  const [tipoNegocio, setTipoNegocio] = useState('')
  const [localizacion, setLocalizacion] = useState('')
  const [enriquecer, setEnriquecer] = useState(false)
  const [etiqueta, setEtiqueta] = useState('')

  const [status, setStatus] = useState('idle') // idle | scraping | done | error
  const [enviandoCRM, setEnviandoCRM] = useState(false)
  const [enviandoLeads, setEnviandoLeads] = useState(false)

  const canStart = tipoNegocio.trim() && localizacion.trim() && status !== 'scraping'
  const canSendLeads = status === 'done' && etiqueta.trim() && !enviandoLeads

  const handleStart = async () => {
    if (!canStart) return
    setStatus('scraping')
    try {
      // TODO: conectar con el endpoint del backend cuando esté disponible
      // const res = await fetch(`${API_BASE}/api/leads/scrape`, { ... })
      await new Promise(r => setTimeout(r, 1200))
      setStatus('done')
    } catch (e) {
      console.error(e)
      setStatus('error')
    }
  }

  const handleEnviarCRM = async () => {
    if (!etiqueta.trim()) return
    setEnviandoCRM(true)
    try {
      // TODO: POST a endpoint de CRM
      await new Promise(r => setTimeout(r, 800))
      alert('Etiqueta enviada a CRM de TIBESA')
    } finally {
      setEnviandoCRM(false)
    }
  }

  const handleEnviarLeads = async () => {
    if (!canSendLeads) return
    setEnviandoLeads(true)
    try {
      // TODO: POST a endpoint de sistema de leads
      await new Promise(r => setTimeout(r, 800))
      alert('Leads enviados al Sistema de Leads')
    } finally {
      setEnviandoLeads(false)
    }
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-gray-900 mb-1">Nueva Búsqueda de Leads</h1>
        <p className="text-sm text-gray-500">Encuentra y enriquece datos de contacto empresarial</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Panel izquierdo: Parámetros */}
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-5">Parámetros de Búsqueda</h2>

          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Tipo de Negocio <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={tipoNegocio}
                onChange={(e) => setTipoNegocio(e.target.value)}
                placeholder="Ej: Peluquería"
                disabled={status === 'scraping'}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-400 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Localización <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={localizacion}
                onChange={(e) => setLocalizacion(e.target.value)}
                placeholder="Ej: Miraflores, Lima, Perú"
                disabled={status === 'scraping'}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-400 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-500"
              />
            </div>

            <label className="flex items-start gap-2 cursor-pointer select-none py-1">
              <input
                type="checkbox"
                checked={enriquecer}
                onChange={(e) => setEnriquecer(e.target.checked)}
                disabled={status === 'scraping'}
                className="mt-0.5 w-4 h-4 rounded border-gray-300 text-sky-500 focus:ring-sky-400"
              />
              <span className="text-sm text-gray-700">
                Enriquecer con Datos Premium (Ejm: Emails, Perfil LinkedIn, etc)
              </span>
            </label>

            <button
              onClick={handleStart}
              disabled={!canStart}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-sky-500 hover:bg-sky-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors cursor-pointer"
            >
              {status === 'scraping' ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Scrapeando...</>
              ) : (
                <><Play className="w-4 h-4" /> Iniciar Scraping</>
              )}
            </button>

            {status === 'done' && (
              <div className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
                Scrapeo completado. Ya puedes enviar los leads.
              </div>
            )}
            {status === 'error' && (
              <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                Ocurrió un error durante el scrapeo.
              </div>
            )}
          </div>
        </div>

        {/* Panel derecho: Etiqueta CRM */}
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-1">Etiqueta para CRM de TIBESA</h2>
          <p className="text-sm text-gray-500 mb-5">Identifica y organiza tus leads en el CRM</p>

          <div className="space-y-4">
            <div>
              <input
                type="text"
                value={etiqueta}
                onChange={(e) => setEtiqueta(e.target.value.slice(0, MAX_ETIQUETA_LEN))}
                placeholder="Ej: Leads Peluquerias Lima - Enero 2025"
                maxLength={MAX_ETIQUETA_LEN}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-400 focus:border-transparent"
              />
              <p className="text-xs text-gray-500 mt-1.5">
                Esta etiqueta te ayudará a identificar y organizar tus leads en CRM de TIBESA (máx. {MAX_ETIQUETA_LEN} caracteres)
              </p>
            </div>

            <button
              onClick={handleEnviarCRM}
              disabled={!etiqueta.trim() || enviandoCRM}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-emerald-500 hover:bg-emerald-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors cursor-pointer"
            >
              {enviandoCRM ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Enviando...</>
              ) : (
                <><Send className="w-4 h-4" /> Enviar a CRM de TIBESA</>
              )}
            </button>

            <button
              onClick={handleEnviarLeads}
              disabled={!canSendLeads}
              className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-indigo-400 hover:bg-indigo-500 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors cursor-pointer"
            >
              {enviandoLeads ? (
                <><Loader2 className="w-4 h-4 animate-spin" /> Enviando...</>
              ) : (
                <><Database className="w-4 h-4" /> Enviar a Sistema de Leads</>
              )}
            </button>

            <div className="text-xs text-gray-500 bg-gray-50 border border-gray-200 rounded-lg px-3 py-2 flex items-start gap-2">
              <span className="text-gray-400 mt-0.5">ⓘ</span>
              <span>Esta opción solo se habilita una vez que se termine el scrapeo de los Leads</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
