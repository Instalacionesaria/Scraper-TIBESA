import { useState } from 'react'
import { Facebook, Play, Loader2, Send, Info } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'
const MAX_ETIQUETA_LEN = 30

export default function ScrappersFacebookPage() {
  const [urlBiblioteca, setUrlBiblioteca] = useState('')
  const [etiqueta, setEtiqueta] = useState('')

  const [statusBiblioteca, setStatusBiblioteca] = useState('idle') // idle | running | done | error
  const [statusPaginas, setStatusPaginas] = useState('idle')
  const [enviandoCRM, setEnviandoCRM] = useState(false)

  const canScrapeBiblioteca = urlBiblioteca.trim() && statusBiblioteca !== 'running'
  const canScrapePaginas = statusBiblioteca === 'done' && statusPaginas !== 'running'
  const canSendCRM = statusPaginas === 'done' && etiqueta.trim() && !enviandoCRM

  const handleScrapeBiblioteca = async () => {
    if (!canScrapeBiblioteca) return
    setStatusBiblioteca('running')
    try {
      // TODO: conectar con endpoint del backend
      // const res = await fetch(`${API_BASE}/api/facebook/biblioteca`, { ... })
      await new Promise(r => setTimeout(r, 1200))
      setStatusBiblioteca('done')
    } catch (e) {
      console.error(e)
      setStatusBiblioteca('error')
    }
  }

  const handleScrapePaginas = async () => {
    if (!canScrapePaginas) return
    setStatusPaginas('running')
    try {
      // TODO: conectar con endpoint del backend
      // const res = await fetch(`${API_BASE}/api/facebook/paginas`, { ... })
      await new Promise(r => setTimeout(r, 1200))
      setStatusPaginas('done')
    } catch (e) {
      console.error(e)
      setStatusPaginas('error')
    }
  }

  const handleEnviarCRM = async () => {
    if (!canSendCRM) return
    setEnviandoCRM(true)
    try {
      // TODO: POST a endpoint de CRM
      await new Promise(r => setTimeout(r, 800))
      alert('Etiqueta enviada a CRM de TIBESA')
    } finally {
      setEnviandoCRM(false)
    }
  }

  return (
    <div className="flex gap-6 -mr-8 min-h-[calc(100vh-4rem)]">
      {/* Contenido principal */}
      <div className="flex-1">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-1">Scrappers de Facebook</h1>
          <p className="text-sm text-gray-500">Extrae leads de la biblioteca de anuncios de Facebook</p>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Card 1: Biblioteca de anuncios */}
          <div className="bg-white border border-gray-200 rounded-xl p-6">
            <h2 className="text-base font-semibold text-gray-800 mb-5">Ingresa la URL de la biblioteca de anuncios</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">
                  URL de la biblioteca de anuncios de Facebook
                </label>
                <input
                  type="url"
                  value={urlBiblioteca}
                  onChange={(e) => setUrlBiblioteca(e.target.value)}
                  placeholder="https://www.facebook.com/ads/library/..."
                  disabled={statusBiblioteca === 'running'}
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-400 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-500"
                />
              </div>

              <button
                onClick={handleScrapeBiblioteca}
                disabled={!canScrapeBiblioteca}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-sky-500 hover:bg-sky-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors cursor-pointer"
              >
                {statusBiblioteca === 'running' ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Scrapeando...</>
                ) : (
                  <><Play className="w-4 h-4" /> Iniciar scraping de esta biblioteca de anuncios</>
                )}
              </button>

              {statusBiblioteca === 'done' && (
                <div className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
                  Biblioteca scrapeada. Ya puedes procesar las páginas.
                </div>
              )}
              {statusBiblioteca === 'error' && (
                <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  Ocurrió un error scrapeando la biblioteca.
                </div>
              )}
            </div>
          </div>

          {/* Card 2: Páginas de Facebook */}
          <div className="bg-white border border-gray-200 rounded-xl p-6">
            <h2 className="text-base font-semibold text-gray-800 mb-5">Scraper de Página de Facebook</h2>

            <div className="space-y-4">
              <div className="flex items-start gap-2 text-sm text-sky-800 bg-sky-50 border border-sky-200 rounded-lg px-3 py-2.5">
                <Info className="w-4 h-4 mt-0.5 shrink-0 text-sky-500" />
                <span>
                  {statusBiblioteca === 'done'
                    ? 'Ya puedes iniciar el scraping de las páginas obtenidas.'
                    : 'Primero completa el scraping de la biblioteca de anuncios para obtener las páginas a procesar.'}
                </span>
              </div>

              <button
                onClick={handleScrapePaginas}
                disabled={!canScrapePaginas}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-indigo-400 hover:bg-indigo-500 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors cursor-pointer"
              >
                {statusPaginas === 'running' ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Scrapeando...</>
                ) : (
                  <><Facebook className="w-4 h-4" /> Iniciar Scraping de las Páginas de Facebook</>
                )}
              </button>

              {statusPaginas === 'done' && (
                <div className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
                  Páginas scrapeadas. Ya puedes enviar los leads al CRM.
                </div>
              )}
              {statusPaginas === 'error' && (
                <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  Ocurrió un error scrapeando las páginas.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Panel lateral oscuro: Etiqueta CRM */}
      <aside className="w-72 bg-[#2c3e50] text-white p-6 shrink-0">
        <h2 className="text-lg font-semibold mb-1">Etiqueta para CRM de TIBESA</h2>
        <p className="text-sm text-white/70 mb-5">Identifica y organiza tus leads en el CRM</p>

        <div className="space-y-4">
          <div>
            <input
              type="text"
              value={etiqueta}
              onChange={(e) => setEtiqueta(e.target.value.slice(0, MAX_ETIQUETA_LEN))}
              placeholder="Ej: Leads Peluquerias Lima - Enero 2025"
              maxLength={MAX_ETIQUETA_LEN}
              className="w-full px-3 py-2.5 bg-white/10 border border-white/20 rounded-lg text-sm text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-sky-400 focus:border-transparent"
            />
            <p className="text-xs text-white/50 mt-1.5">
              Esta etiqueta te ayudará a identificar y organizar tus leads en CRM de TIBESA (máx. {MAX_ETIQUETA_LEN} caracteres)
            </p>
          </div>

          <button
            onClick={handleEnviarCRM}
            disabled={!canSendCRM}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-emerald-500 hover:bg-emerald-600 disabled:bg-white/10 disabled:text-white/40 disabled:cursor-not-allowed transition-colors cursor-pointer"
          >
            {enviandoCRM ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Enviando...</>
            ) : (
              <><Send className="w-4 h-4" /> Enviar a CRM de TIBESA</>
            )}
          </button>

          <div className="text-xs text-white/60 bg-white/5 border border-white/10 rounded-lg px-3 py-2 flex items-start gap-2">
            <Info className="w-3.5 h-3.5 mt-0.5 shrink-0 text-white/40" />
            <span>Esta opción solo se habilita una vez que se termine el scrapeo de los Leads</span>
          </div>
        </div>
      </aside>
    </div>
  )
}
