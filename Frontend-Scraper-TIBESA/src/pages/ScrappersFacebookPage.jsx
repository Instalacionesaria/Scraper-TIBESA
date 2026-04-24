import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Facebook, Play, Loader2, Send, Info, AlertTriangle, Download, Share2 } from 'lucide-react'
import { getCredentials } from '../lib/auth'
import {
  startFacebookAds,
  startFacebookPages,
  pollJobUntilDone,
  sendToCrm,
  sendToSistemaLeads,
} from '../lib/leadsApi'
import { downloadCsv } from '../lib/csv'
import LeadsTable from '../components/LeadsTable'

const MAX_ETIQUETA_LEN = 30

export default function ScrappersFacebookPage() {
  const [urlBiblioteca, setUrlBiblioteca] = useState('')
  const [etiqueta, setEtiqueta] = useState('')

  // Paso 1: biblioteca de anuncios → obtiene lista de páginas
  const [statusAds, setStatusAds] = useState('idle') // idle | running | done | error
  const [adsJobId, setAdsJobId] = useState(null)
  const [adsPages, setAdsPages] = useState([]) // páginas extraídas para paso 2
  const [errorAds, setErrorAds] = useState('')

  // Paso 2: scrapeo de cada página
  const [statusPages, setStatusPages] = useState('idle')
  const [pagesJobId, setPagesJobId] = useState(null)
  const [pagesCount, setPagesCount] = useState(0)
  const [pagesData, setPagesData] = useState([])
  const [errorPages, setErrorPages] = useState('')

  // Paso 3: CRM
  const [enviandoCRM, setEnviandoCRM] = useState(false)
  const [crmResult, setCrmResult] = useState(null)
  const [enviandoSL, setEnviandoSL] = useState(false)
  const [slResult, setSlResult] = useState(null)

  const credentials = getCredentials()
  const hasAuth = !!credentials

  const canScrapeAds = hasAuth && urlBiblioteca.trim() && statusAds !== 'running'
  const canScrapePages = statusAds === 'done' && adsPages.length > 0 && statusPages !== 'running'
  const canSendCRM = statusPages === 'done' && etiqueta.trim() && !enviandoCRM && pagesJobId
  const canSendSL = statusPages === 'done' && !enviandoSL && pagesJobId
  const canDownloadCsv = statusPages === 'done' && pagesData.length > 0

  const handleScrapeAds = async () => {
    if (!canScrapeAds) return
    setStatusAds('running')
    setErrorAds('')
    setAdsPages([])
    setStatusPages('idle')
    setPagesJobId(null)
    setPagesCount(0)
    setCrmResult(null)

    try {
      const { jobId } = await startFacebookAds({ url: urlBiblioteca.trim(), credentials })
      setAdsJobId(jobId)

      const job = await pollJobUntilDone(jobId)
      if (job.status !== 'COMPLETED') {
        setErrorAds(`El trabajo terminó con estado: ${job.status}`)
        setStatusAds('error')
        return
      }

      const pages = job.results?.data || []
      if (pages.length === 0) {
        setErrorAds('La biblioteca no devolvió páginas para scrapear.')
        setStatusAds('error')
        return
      }
      setAdsPages(pages)
      setStatusAds('done')
    } catch (e) {
      console.error(e)
      setErrorAds(e.message || 'Error desconocido')
      setStatusAds('error')
    }
  }

  const handleScrapePages = async () => {
    if (!canScrapePages) return
    setStatusPages('running')
    setErrorPages('')
    setPagesData([])
    setCrmResult(null)

    try {
      const { jobId } = await startFacebookPages({ pages: adsPages, credentials })
      setPagesJobId(jobId)

      const job = await pollJobUntilDone(jobId)
      if (job.status !== 'COMPLETED') {
        setErrorPages(`El trabajo terminó con estado: ${job.status}`)
        setStatusPages('error')
        return
      }
      setPagesCount(job.results_count || 0)
      setPagesData(job.results?.data || [])
      setStatusPages('done')
    } catch (e) {
      console.error(e)
      setErrorPages(e.message || 'Error desconocido')
      setStatusPages('error')
    }
  }

  const handleDownloadCsv = () => {
    if (!canDownloadCsv) return
    downloadCsv(pagesData, `facebook-pages-${pagesJobId?.slice(0, 8) || Date.now()}.csv`)
  }

  const handleEnviarSistema = async () => {
    if (!canSendSL) return
    setEnviandoSL(true)
    setSlResult(null)
    try {
      const res = await sendToSistemaLeads({ jobId: pagesJobId, credentials })
      setSlResult(res)
    } catch (e) {
      setSlResult({ status: 'error', message: e.message })
    } finally {
      setEnviandoSL(false)
    }
  }

  const handleEnviarCRM = async () => {
    if (!canSendCRM) return
    setEnviandoCRM(true)
    setCrmResult(null)
    try {
      const res = await sendToCrm({ jobId: pagesJobId, etiqueta: etiqueta.trim(), credentials })
      setCrmResult(res)
    } catch (e) {
      setCrmResult({ status: 'error', message: e.message })
    } finally {
      setEnviandoCRM(false)
    }
  }

  return (
    <div className="flex gap-6 -mr-8 min-h-[calc(100vh-4rem)]">
      <div className="flex-1 min-w-0 overflow-hidden">
        <div className="mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-1">Scrappers de Facebook</h1>
          <p className="text-sm text-gray-500">Extrae leads de la biblioteca de anuncios de Facebook</p>
        </div>

        {!hasAuth && (
          <div className="mb-6 flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-800">
            <AlertTriangle className="w-5 h-5 shrink-0 text-amber-500 mt-0.5" />
            <div>
              Aún no has configurado tus credenciales TIBESA.{' '}
              <Link to="/configuracion" className="underline font-medium">Ir a Configuración</Link> para guardarlas.
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Paso 1 */}
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
                  disabled={statusAds === 'running'}
                  className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-400 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-500"
                />
              </div>

              <button
                onClick={handleScrapeAds}
                disabled={!canScrapeAds}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-sky-500 hover:bg-sky-600 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors cursor-pointer"
              >
                {statusAds === 'running' ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Scrapeando biblioteca...</>
                ) : (
                  <><Play className="w-4 h-4" /> Iniciar scraping de esta biblioteca de anuncios</>
                )}
              </button>

              {statusAds === 'done' && (
                <div className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
                  <strong>{adsPages.length}</strong> páginas detectadas. Ya puedes procesarlas.
                </div>
              )}
              {statusAds === 'error' && (
                <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  {errorAds || 'Ocurrió un error scrapeando la biblioteca.'}
                </div>
              )}
            </div>
          </div>

          {/* Paso 2 */}
          <div className="bg-white border border-gray-200 rounded-xl p-6">
            <h2 className="text-base font-semibold text-gray-800 mb-5">Scraper de Página de Facebook</h2>

            <div className="space-y-4">
              <div className="flex items-start gap-2 text-sm text-sky-800 bg-sky-50 border border-sky-200 rounded-lg px-3 py-2.5">
                <Info className="w-4 h-4 mt-0.5 shrink-0 text-sky-500" />
                <span>
                  {statusAds === 'done'
                    ? `Ya puedes iniciar el scraping de ${adsPages.length} páginas obtenidas.`
                    : 'Primero completa el scraping de la biblioteca de anuncios para obtener las páginas a procesar.'}
                </span>
              </div>

              <button
                onClick={handleScrapePages}
                disabled={!canScrapePages}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-indigo-400 hover:bg-indigo-500 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors cursor-pointer"
              >
                {statusPages === 'running' ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Scrapeando páginas...</>
                ) : (
                  <><Facebook className="w-4 h-4" /> Iniciar Scraping de las Páginas de Facebook</>
                )}
              </button>

              {statusPages === 'done' && (
                <div className="text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
                  <strong>{pagesCount}</strong> páginas scrapeadas. Ya puedes enviar los leads al CRM.
                </div>
              )}
              {statusPages === 'error' && (
                <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                  {errorPages || 'Ocurrió un error scrapeando las páginas.'}
                </div>
              )}
            </div>
          </div>
        </div>

        {statusAds === 'done' && adsPages.length > 0 && statusPages !== 'done' && (
          <LeadsTable rows={adsPages} title={`Páginas detectadas (${adsPages.length})`} />
        )}

        {statusPages === 'done' && pagesData.length > 0 && (
          <LeadsTable rows={pagesData} title="Páginas de Facebook scrapeadas" />
        )}
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
            onClick={handleDownloadCsv}
            disabled={!canDownloadCsv}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-sky-500 hover:bg-sky-600 disabled:bg-white/10 disabled:text-white/40 disabled:cursor-not-allowed transition-colors cursor-pointer"
          >
            <Download className="w-4 h-4" /> Descargar CSV
          </button>

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

          {crmResult && (
            <div className={`text-xs rounded-lg px-3 py-2 border ${
              crmResult.status === 'success'
                ? 'text-green-200 bg-green-500/10 border-green-500/30'
                : 'text-red-200 bg-red-500/10 border-red-500/30'
            }`}>
              {crmResult.message}
              {typeof crmResult.leads_sent === 'number' && (
                <span className="block mt-1">Enviados: {crmResult.leads_sent}</span>
              )}
            </div>
          )}

          <button
            onClick={handleEnviarSistema}
            disabled={!canSendSL}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-indigo-400 hover:bg-indigo-500 disabled:bg-white/10 disabled:text-white/40 disabled:cursor-not-allowed transition-colors cursor-pointer"
          >
            {enviandoSL ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Enviando al Sistema...</>
            ) : (
              <><Share2 className="w-4 h-4" /> Enviar a Sistema de Leads</>
            )}
          </button>

          {slResult && (
            <div className={`text-xs rounded-lg px-3 py-2 border ${
              slResult.status === 'success'
                ? 'text-indigo-200 bg-indigo-500/10 border-indigo-400/30'
                : 'text-red-200 bg-red-500/10 border-red-500/30'
            }`}>
              {slResult.message}
              {typeof slResult.leads_sent === 'number' && (
                <span className="block mt-1">
                  Enviados: {slResult.leads_sent}
                  {typeof slResult.leads_failed === 'number' && slResult.leads_failed > 0 && (
                    <> · Fallaron: {slResult.leads_failed}</>
                  )}
                </span>
              )}
            </div>
          )}

          <div className="text-xs text-white/60 bg-white/5 border border-white/10 rounded-lg px-3 py-2 flex items-start gap-2">
            <Info className="w-3.5 h-3.5 mt-0.5 shrink-0 text-white/40" />
            <span>Esta opción solo se habilita una vez que se termine el scrapeo de los Leads</span>
          </div>
        </div>
      </aside>
    </div>
  )
}
