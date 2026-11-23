import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Link } from 'react-router-dom'
import { LineChart, Send, Loader2, Bot, User, RotateCcw, History, Trash2, ArrowLeft, MessageSquare, BarChart3, FileDown, CheckCircle2, X } from 'lucide-react'
import PanelGraficos from '../components/PanelGraficos'
import { getCredentials } from '../lib/auth'
import {
  askAnalistaMercado, borrarConversacion, descargarArchivo, generarInforme, getConversacion, getPanorama,
  getResumenMercado, listarConversaciones,
} from '../lib/mercadoApi'

// Solo guardamos el id de la conversación actual; los mensajes viven en el backend (checkpointer).
const THREAD_KEY = 'analista-mercado-thread'

const SUGERENCIAS = [
  '¿Cuánto cuesta el m² de terreno en cada zona de Mazatlán?',
  'Compare Cerritos, Marina y El Cid para comprar una casa',
  '¿Qué zona está más barata para comprar casa?',
  'Muéstreme oportunidades de terrenos con buen precio por m²',
  'Quiero vender una casa de 3 recámaras en Real del Valle, ¿en cuánto la publico?',
  '¿Cuánto cuesta la hectárea en ranchos o terrenos grandes?',
]

// Estilos para la respuesta en Markdown (tablas, listas, enlaces) con letra grande.
const MD = {
  p: (props) => <p className="mb-3 last:mb-0" {...props} />,
  ul: (props) => <ul className="mb-3 list-disc space-y-1.5 pl-6" {...props} />,
  ol: (props) => <ol className="mb-3 list-decimal space-y-1.5 pl-6" {...props} />,
  strong: (props) => <strong className="font-semibold text-gray-900" {...props} />,
  a: (props) => (
    <a {...props} target="_blank" rel="noopener noreferrer" className="font-medium text-emerald-700 underline hover:text-emerald-900" />
  ),
  table: (props) => (
    <div className="mb-3 overflow-x-auto rounded-lg border border-gray-200">
      <table className="min-w-full text-left text-[15px]" {...props} />
    </div>
  ),
  thead: (props) => <thead className="bg-gray-100 text-gray-700" {...props} />,
  th: (props) => <th className="whitespace-nowrap px-3 py-2 font-semibold" {...props} />,
  td: (props) => <td className="border-t border-gray-100 px-3 py-2 align-top" {...props} />,
}

function nuevoId() {
  return globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function leerThread() {
  try {
    return localStorage.getItem(THREAD_KEY)
  } catch {
    return null
  }
}

function guardarThread(id) {
  try {
    localStorage.setItem(THREAD_KEY, id)
  } catch {
    // sin almacenamiento: la conversación sigue guardada en el servidor, solo no se reabre sola
  }
}

function formatearFechaHora(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? ''
    : d.toLocaleString('es-MX', { day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit' })
}

function formatearFecha(iso) {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d.toLocaleDateString('es-MX', { day: 'numeric', month: 'long', year: 'numeric' })
}

export default function AnalistaMercadoPage() {
  const usuario = getCredentials()?.correo_electronico || null
  const [threadId, setThreadId] = useState(() => leerThread() || nuevoId())
  const [mensajes, setMensajes] = useState([])
  const [cargando, setCargando] = useState(true)
  const [input, setInput] = useState('')
  const [pensando, setPensando] = useState(false)
  const [resumen, setResumen] = useState(null)
  const [vista, setVista] = useState('chat') // chat | historial
  const [historial, setHistorial] = useState(null)
  const [panorama, setPanorama] = useState(null) // gráficos generales
  const [seleccion, setSeleccion] = useState(null) // índice del mensaje cuyos gráficos se ven; null = panorama
  const [informe, setInforme] = useState({ estado: 'idle' }) // idle | generando | listo | error
  const finRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    getResumenMercado().then(setResumen).catch(() => setResumen(null))
    getPanorama().then((p) => setPanorama(p.graficos || [])).catch(() => setPanorama([]))
  }, [])

  // Índice de la última respuesta con gráficos (la que se muestra por defecto).
  const ultimaConGraficos = (lista) => {
    for (let i = lista.length - 1; i >= 0; i -= 1) {
      if (lista[i].role === 'assistant' && lista[i].graficos?.length) return i
    }
    return null
  }

  // Al entrar, retomar la última conversación guardada en el servidor.
  useEffect(() => {
    guardarThread(threadId)
    let activo = true
    setCargando(true)
    getConversacion(threadId, usuario)
      .then((c) => {
        if (!activo) return
        const lista = c.mensajes || []
        setMensajes(lista)
        setSeleccion(ultimaConGraficos(lista))
      })
      .catch(() => { if (activo) { setMensajes([]); setSeleccion(null) } })
      .finally(() => { if (activo) setCargando(false) })
    return () => { activo = false }
  }, [threadId, usuario])

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [mensajes, pensando])

  const abrirHistorial = async () => {
    setVista('historial')
    setHistorial(null)
    try {
      const { conversaciones } = await listarConversaciones(usuario)
      setHistorial(conversaciones || [])
    } catch {
      setHistorial([])
    }
  }

  const abrirConversacion = (id) => {
    setThreadId(id)
    setVista('chat')
  }

  const eliminarConversacion = async (id) => {
    if (!window.confirm('¿Seguro que desea borrar esta conversación? No se puede recuperar.')) return
    try {
      await borrarConversacion(id, usuario)
      setHistorial((prev) => (prev || []).filter((c) => c.thread_id !== id))
      if (id === threadId) setThreadId(nuevoId())
    } catch (e) {
      window.alert(`No se pudo borrar: ${e.message}`)
    }
  }

  const preguntar = async (texto) => {
    const pregunta = (texto ?? input).trim()
    if (!pregunta || pensando) return
    setMensajes((prev) => [...prev, { role: 'user', content: pregunta }])
    setInput('')
    setPensando(true)
    try {
      const { response, graficos } = await askAnalistaMercado({ threadId, mensaje: pregunta, usuario })
      setMensajes((prev) => [...prev, { role: 'assistant', content: response, graficos: graficos || [] }])
      // índice de la respuesta: mensajes previos + la pregunta recién agregada
      if (graficos?.length) setSeleccion(mensajes.length + 1)
    } catch (e) {
      setMensajes((prev) => [
        ...prev,
        { role: 'assistant', error: true, content: `No pude responder en este momento (${e.message}). Por favor, intente de nuevo en un momento.` },
      ])
    } finally {
      setPensando(false)
      inputRef.current?.focus()
    }
  }

  const nuevaConversacion = () => {
    setThreadId(nuevoId())
    setMensajes([])
    setSeleccion(null)
    setInforme({ estado: 'idle' })
    setInput('')
    setVista('chat')
    inputRef.current?.focus()
  }

  const descargarInforme = async () => {
    setInforme({ estado: 'generando' })
    try {
      const meta = await generarInforme({ threadId, usuario })
      descargarArchivo(meta.download_url)
      setInforme({ estado: 'listo', meta })
    } catch (e) {
      setInforme({ estado: 'error', mensaje: e.message })
    }
  }

  const fecha = formatearFecha(resumen?.actualizado)
  const hayRespuestas = mensajes.some((m) => m.role === 'assistant' && !m.error)
  const vacia = mensajes.length === 0
  const graficosRespuesta = seleccion !== null ? mensajes[seleccion]?.graficos : null
  const ultimaIdx = ultimaConGraficos(mensajes)

  return (
    <div className="mx-auto flex min-h-[calc(100vh-4rem)] max-w-[1600px] flex-col lg:h-[calc(100vh-4rem)]">
      {/* Cabecera */}
      <div className="mb-5 flex items-start justify-between gap-4">
        <div className="flex items-start gap-4">
          <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-emerald-100">
            <LineChart className="h-7 w-7 text-emerald-700" />
          </div>
          <div>
            <h1 className="text-3xl font-bold text-gray-900">Analista de Mercado</h1>
            <p className="mt-1 text-base text-gray-600">
              {resumen
                ? <>Pregunte lo que quiera sobre las <strong>{resumen.propiedades.toLocaleString('es-MX')} propiedades</strong> de {resumen.portales} portales{fecha && <> (datos al {fecha})</>}.</>
                : 'Pregunte lo que quiera sobre las propiedades de todos los portales.'}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap justify-end gap-2">
          {vista === 'chat' && hayRespuestas && (
            <button
              onClick={descargarInforme}
              disabled={pensando || informe.estado === 'generando'}
              title="Arma un informe en PDF con lo conversado y sus gráficos"
              className="inline-flex items-center gap-2 rounded-xl bg-[#0B2545] px-4 py-2.5 text-base font-medium text-white hover:bg-[#13315C] disabled:opacity-60 cursor-pointer"
            >
              {informe.estado === 'generando'
                ? <><Loader2 className="h-5 w-5 animate-spin" /> Preparando su informe…</>
                : <><FileDown className="h-5 w-5" /> Descargar informe (PDF)</>}
            </button>
          )}
          {vista === 'chat' ? (
            <button
              onClick={abrirHistorial}
              disabled={pensando}
              className="inline-flex items-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-base font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 cursor-pointer"
            >
              <History className="h-5 w-5" /> Conversaciones anteriores
            </button>
          ) : (
            <button
              onClick={() => setVista('chat')}
              className="inline-flex items-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-base font-medium text-gray-700 hover:bg-gray-50 cursor-pointer"
            >
              <ArrowLeft className="h-5 w-5" /> Volver a la conversación
            </button>
          )}
          {(!vacia || vista === 'historial') && (
            <button
              onClick={nuevaConversacion}
              disabled={pensando}
              className="inline-flex items-center gap-2 rounded-xl border border-emerald-300 bg-emerald-50 px-4 py-2.5 text-base font-medium text-emerald-800 hover:bg-emerald-100 disabled:opacity-50 cursor-pointer"
            >
              <RotateCcw className="h-5 w-5" /> Nueva conversación
            </button>
          )}
        </div>
      </div>

      {informe.estado === 'listo' && (
        <div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-base text-emerald-900">
          <span className="inline-flex items-center gap-2">
            <CheckCircle2 className="h-5 w-5 shrink-0 text-emerald-600" />
            <span>
              Su informe <strong>«{informe.meta.titulo}»</strong> se descargó. También quedó guardado en{' '}
              <Link to="/resultados" className="font-semibold underline">Resultados</Link>.
            </span>
          </span>
          <span className="flex shrink-0 items-center gap-2">
            <button onClick={() => descargarArchivo(informe.meta.download_url)} className="rounded-lg border border-emerald-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-emerald-100 cursor-pointer">
              Descargar de nuevo
            </button>
            <button onClick={() => setInforme({ estado: 'idle' })} aria-label="Cerrar aviso" className="rounded-full p-1 text-emerald-700 hover:bg-emerald-100 cursor-pointer">
              <X className="h-5 w-5" />
            </button>
          </span>
        </div>
      )}
      {informe.estado === 'error' && (
        <div className="mb-4 flex items-center justify-between gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-base text-red-800">
          <span>No se pudo preparar el informe ({informe.mensaje}). Por favor, intente de nuevo.</span>
          <button onClick={() => setInforme({ estado: 'idle' })} aria-label="Cerrar aviso" className="rounded-full p-1 hover:bg-red-100 cursor-pointer">
            <X className="h-5 w-5" />
          </button>
        </div>
      )}

      <div className="grid min-h-0 flex-1 gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
      {/* Columna izquierda: chat */}
      <div className="flex min-h-[70vh] flex-col lg:min-h-0">
      {/* Conversación */}
      <div className="flex-1 overflow-y-auto rounded-2xl border border-gray-200 bg-white p-6">
        {vista === 'historial' ? (
          <div>
            <p className="mb-4 text-lg font-semibold text-gray-800">Sus conversaciones anteriores</p>
            {historial === null ? (
              <div className="inline-flex items-center gap-2 text-base text-gray-600">
                <Loader2 className="h-5 w-5 animate-spin text-emerald-600" /> Cargando…
              </div>
            ) : historial.length === 0 ? (
              <p className="text-base text-gray-600">Todavía no tiene conversaciones guardadas.</p>
            ) : (
              <ul className="space-y-3">
                {historial.map((c) => (
                  <li key={c.thread_id} className={`flex items-stretch gap-2 rounded-xl border ${c.thread_id === threadId ? 'border-emerald-300 bg-emerald-50' : 'border-gray-200 bg-white'}`}>
                    <button
                      onClick={() => abrirConversacion(c.thread_id)}
                      className="flex flex-1 items-start gap-3 px-4 py-3.5 text-left hover:bg-gray-50 rounded-l-xl cursor-pointer"
                    >
                      <MessageSquare className="mt-0.5 h-5 w-5 shrink-0 text-emerald-700" />
                      <span>
                        <span className="block text-base font-medium text-gray-900">{c.titulo || '(sin preguntas)'}</span>
                        <span className="block text-sm text-gray-500">
                          {formatearFechaHora(c.actualizado)} · {c.preguntas} {c.preguntas === 1 ? 'pregunta' : 'preguntas'}
                        </span>
                      </span>
                    </button>
                    <button
                      onClick={() => eliminarConversacion(c.thread_id)}
                      aria-label="Borrar conversación"
                      title="Borrar conversación"
                      className="px-4 text-gray-400 hover:text-red-600 cursor-pointer"
                    >
                      <Trash2 className="h-5 w-5" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : cargando ? (
          <div className="inline-flex items-center gap-2 text-base text-gray-600">
            <Loader2 className="h-5 w-5 animate-spin text-emerald-600" /> Cargando su conversación…
          </div>
        ) : vacia ? (
          <div>
            <p className="mb-2 text-lg font-semibold text-gray-800">¿Qué le gustaría saber del mercado?</p>
            <p className="mb-5 text-base text-gray-600">
              Escriba su pregunta abajo o haga clic en una de estas:
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              {SUGERENCIAS.map((s) => (
                <button
                  key={s}
                  onClick={() => preguntar(s)}
                  className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3.5 text-left text-base text-emerald-900 hover:bg-emerald-100 cursor-pointer"
                >
                  {s}
                </button>
              ))}
            </div>
            <p className="mt-6 text-sm text-gray-500">
              Los precios son los publicados en los portales (precio de lista), no el precio final de venta.
            </p>
          </div>
        ) : (
          <div className="space-y-5">
            {mensajes.map((m, i) => (
              <div key={i} className={`flex gap-3 ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {m.role === 'assistant' && (
                  <div className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-100">
                    <Bot className="h-5 w-5 text-emerald-700" />
                  </div>
                )}
                <div
                  className={`max-w-[85%] rounded-2xl px-5 py-3.5 text-base leading-relaxed ${
                    m.role === 'user'
                      ? 'rounded-br-md bg-[#2c3e50] text-white'
                      : m.error
                        ? 'rounded-bl-md border border-red-200 bg-red-50 text-red-800'
                        : 'rounded-bl-md border border-gray-200 bg-gray-50 text-gray-800'
                  }`}
                >
                  {m.role === 'assistant' && !m.error
                    ? <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD}>{m.content}</ReactMarkdown>
                    : m.content}
                  {m.role === 'assistant' && m.graficos?.length > 0 && (
                    <button
                      onClick={() => setSeleccion(i)}
                      className={`mt-3 inline-flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-sm font-medium cursor-pointer ${
                        seleccion === i
                          ? 'border-emerald-300 bg-emerald-50 text-emerald-800'
                          : 'border-gray-300 bg-white text-gray-700 hover:bg-gray-50'
                      }`}
                    >
                      <BarChart3 className="h-4 w-4" />
                      {seleccion === i ? 'Gráfico a la derecha' : 'Ver gráfico'}
                    </button>
                  )}
                </div>
                {m.role === 'user' && (
                  <div className="mt-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gray-200">
                    <User className="h-5 w-5 text-gray-500" />
                  </div>
                )}
              </div>
            ))}
            {pensando && (
              <div className="flex items-center gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-emerald-100">
                  <Bot className="h-5 w-5 text-emerald-700" />
                </div>
                <div className="inline-flex items-center gap-2 rounded-2xl rounded-bl-md border border-gray-200 bg-gray-50 px-5 py-3.5 text-base text-gray-600">
                  <Loader2 className="h-5 w-5 animate-spin text-emerald-600" />
                  Analizando las propiedades… (puede tardar unos segundos)
                </div>
              </div>
            )}
            <div ref={finRef} />
          </div>
        )}
      </div>

      {/* Caja de pregunta */}
      <form
        onSubmit={(e) => { e.preventDefault(); preguntar() }}
        className="mt-4 flex gap-3"
      >
        <input
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={pensando || vista === 'historial'}
          placeholder="Escriba aquí su pregunta. Ej: ¿Cuánto cuesta un departamento en la Zona Dorada?"
          className="flex-1 rounded-xl border border-gray-300 bg-white px-5 py-4 text-base focus:border-transparent focus:outline-none focus:ring-2 focus:ring-emerald-400 disabled:bg-gray-50"
        />
        <button
          type="submit"
          disabled={!input.trim() || pensando || vista === 'historial'}
          className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-6 py-4 text-base font-semibold text-white hover:bg-emerald-700 disabled:bg-gray-300 cursor-pointer"
        >
          <Send className="h-5 w-5" /> Preguntar
        </button>
      </form>
      </div>

      {/* Columna derecha: gráficos que complementan la respuesta (o panorama general) */}
      <aside className="min-h-0 rounded-2xl bg-gray-100/70 p-4">
        <PanelGraficos
          modo={graficosRespuesta ? 'respuesta' : 'panorama'}
          graficos={graficosRespuesta || panorama}
          cargando={!graficosRespuesta && panorama === null}
          hayRespuesta={ultimaIdx !== null}
          onVerPanorama={() => setSeleccion(null)}
          onVerRespuesta={() => setSeleccion(ultimaIdx)}
        />
      </aside>
      </div>
    </div>
  )
}
