import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Play, Loader2, Send, AlertTriangle, Download, Share2, Linkedin } from 'lucide-react'
import { getCredentials } from '../lib/auth'
import { startLinkedIn, pollJobUntilDone, sendToCrm, sendToSistemaLeads } from '../lib/leadsApi'
import { downloadCsv } from '../lib/csv'
import LeadsTable from '../components/LeadsTable'

const MAX_ETIQUETA_LEN = 30

export default function ScraperLinkedInPage() {
  const [jobTitle, setJobTitle] = useState('')
  const [country, setCountry] = useState('')
  const [state, setState] = useState('')
  const [numberOfLeads, setNumberOfLeads] = useState(100)
  const [etiqueta, setEtiqueta] = useState('')

  const [status, setStatus] = useState('idle')
  const [jobId, setJobId] = useState(null)
  const [resultsCount, setResultsCount] = useState(0)
  const [leads, setLeads] = useState([])
  const [errorMsg, setErrorMsg] = useState('')

  const [enviandoCRM, setEnviandoCRM] = useState(false)
  const [crmResult, setCrmResult] = useState(null)
  const [enviandoSL, setEnviandoSL] = useState(false)
  const [slResult, setSlResult] = useState(null)

  const credentials = getCredentials()
  const hasAuth = !!credentials

  const canStart = hasAuth && jobTitle.trim() && country.trim() && Number(numberOfLeads) > 0 && status !== 'scraping'
  const canSendCRM = status === 'done' && etiqueta.trim() && !enviandoCRM && jobId
  const canSendSL = status === 'done' && !enviandoSL && jobId
  const canDownloadCsv = status === 'done' && leads.length > 0

  const handleStart = async () => {
    if (!canStart) return
    setStatus('scraping')
    setErrorMsg('')
    setResultsCount(0)
    setLeads([])
    setCrmResult(null)
    setSlResult(null)

    try {
      const { jobId: newJobId } = await startLinkedIn({
        jobTitle: jobTitle.trim(),
        country: country.trim(),
        state: state.trim() || null,
        numberOfLeads: Number(numberOfLeads) || 100,
        credentials,
      })
      setJobId(newJobId)

      const job = await pollJobUntilDone(newJobId, { intervalMs: 5000, timeoutMs: 30 * 60 * 1000 })
      if (job.status === 'COMPLETED') {
        setResultsCount(job.results_count || 0)
        setLeads(job.results?.data || [])
        setStatus('done')
      } else {
        setErrorMsg(`El trabajo terminó con estado: ${job.status}`)
        setStatus('error')
      }
    } catch (e) {
      console.error(e)
      setErrorMsg(e.message || 'Error desconocido')
      setStatus('error')
    }
  }

  const handleDownloadCsv = () => {
    if (!canDownloadCsv) return
    const slug = (jobTitle + '-' + country + '-' + state).trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')
    downloadCsv(leads, `linkedin-${slug || 'tibesa'}-${jobId?.slice(0, 8) || Date.now()}.csv`)
  }

  const handleEnviarSistema = async () => {
    if (!canSendSL) return
    setEnviandoSL(true)
    setSlResult(null)
    try {
      const res = await sendToSistemaLeads({ jobId, credentials })
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
      const res = await sendToCrm({ jobId, etiqueta: etiqueta.trim(), credentials })
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
        <div className="mb-8 flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-[#0a66c2] text-white flex items-center justify-center">
            <Linkedin className="w-5 h-5" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-gray-900 mb-1">Scraper de LinkedIn</h1>
            <p className="text-sm text-gray-500">Encuentra leads por cargo, país y estado (con emails verificados)</p>
          </div>
        </div>

        {!hasAuth && (
          <div className="mb-6 flex items-start gap-3 bg-amber-50 border border-amber-200 rounded-xl px-4 py-3 text-sm text-amber-800">
            <AlertTriangle className="w-5 h-5 shrink-0 text-amber-500 mt-0.5" />
            <div>
              Aún no has configurado tus credenciales TIBESA.{' '}
              <Link to="/configuracion" className="underline font-medium">Ir a Configuración</Link>.
            </div>
          </div>
        )}

        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-gray-800 mb-5">Parámetros de Búsqueda</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Job Title <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={jobTitle}
                onChange={(e) => setJobTitle(e.target.value)}
                placeholder="Ej: Real Estate Agent"
                disabled={status === 'scraping'}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-400 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Country <span className="text-red-500">*</span>
              </label>
              <input
                type="text"
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                placeholder="Ej: United States"
                disabled={status === 'scraping'}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-400 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">State</label>
              <input
                type="text"
                value={state}
                onChange={(e) => setState(e.target.value)}
                placeholder="Ej: California"
                disabled={status === 'scraping'}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-400 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-500"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1.5">
                Number of Leads <span className="text-red-500">*</span>
              </label>
              <input
                type="number"
                min={1}
                max={30000}
                value={numberOfLeads}
                onChange={(e) => setNumberOfLeads(e.target.value)}
                placeholder="100"
                disabled={status === 'scraping'}
                className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-400 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-500"
              />
            </div>
          </div>

          <button
            onClick={handleStart}
            disabled={!canStart}
            className="mt-5 w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-[#0a66c2] hover:bg-[#084c95] disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors cursor-pointer"
          >
            {status === 'scraping' ? (
              <><Loader2 className="w-4 h-4 animate-spin" /> Scrapeando... (puede tardar varios minutos)</>
            ) : (
              <><Play className="w-4 h-4" /> Iniciar Scraping</>
            )}
          </button>

          {status === 'done' && (
            <div className="mt-4 text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg px-3 py-2">
              Scrapeo completado. <strong>{resultsCount}</strong> leads encontrados. Job ID: <code className="text-xs">{jobId}</code>
            </div>
          )}
          {status === 'error' && (
            <div className="mt-4 text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {errorMsg || 'Ocurrió un error durante el scrapeo.'}
            </div>
          )}
        </div>

        {status === 'done' && leads.length > 0 && (
          <LeadsTable rows={leads} title="Leads scrapeados de LinkedIn" />
        )}
      </div>

      {/* Panel lateral oscuro */}
      <aside className="w-72 bg-[#2c3e50] text-white p-6 shrink-0">
        <h2 className="text-lg font-semibold mb-1">Etiqueta para CRM de TIBESA</h2>
        <p className="text-sm text-white/70 mb-5">Identifica y organiza tus leads en el CRM</p>

        <div className="space-y-4">
          <div>
            <input
              type="text"
              value={etiqueta}
              onChange={(e) => setEtiqueta(e.target.value.slice(0, MAX_ETIQUETA_LEN))}
              placeholder="Ej: LinkedIn Real Estate USA - 2026"
              maxLength={MAX_ETIQUETA_LEN}
              className="w-full px-3 py-2.5 bg-white/10 border border-white/20 rounded-lg text-sm text-white placeholder-white/40 focus:outline-none focus:ring-2 focus:ring-sky-400 focus:border-transparent"
            />
            <p className="text-xs text-white/50 mt-1.5">
              Esta etiqueta te ayudará a identificar tus leads en CRM de TIBESA (máx. {MAX_ETIQUETA_LEN} caracteres)
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
            <span className="text-white/40 mt-0.5">ⓘ</span>
            <span>Los botones de envío se habilitan al terminar el scrapeo</span>
          </div>
        </div>
      </aside>
    </div>
  )
}
