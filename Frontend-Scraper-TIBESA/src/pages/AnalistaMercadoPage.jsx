import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { LineChart, Send, Loader2, Bot, User, RotateCcw } from 'lucide-react'
import { askAnalistaMercado, getResumenMercado } from '../lib/mercadoApi'

const STORAGE_KEY = 'analista-mercado-conversacion'

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

function cargarConversacion() {
  try {
    const guardada = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || '[]')
    return Array.isArray(guardada) ? guardada : []
  } catch {
    return []
  }
}

function formatearFecha(iso) {
  if (!iso) return null
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? null : d.toLocaleDateString('es-MX', { day: 'numeric', month: 'long', year: 'numeric' })
}

export default function AnalistaMercadoPage() {
  const [mensajes, setMensajes] = useState(cargarConversacion)
  const [input, setInput] = useState('')
  const [pensando, setPensando] = useState(false)
  const [resumen, setResumen] = useState(null)
  const finRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    getResumenMercado().then(setResumen).catch(() => setResumen(null))
  }, [])

  useEffect(() => {
    try {
      sessionStorage.setItem(STORAGE_KEY, JSON.stringify(mensajes))
    } catch {
      // sin almacenamiento disponible: la conversación solo vive en esta pestaña
    }
    finRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [mensajes, pensando])

  const preguntar = async (texto) => {
    const pregunta = (texto ?? input).trim()
    if (!pregunta || pensando) return
    const historial = [...mensajes, { role: 'user', content: pregunta }]
    setMensajes(historial)
    setInput('')
    setPensando(true)
    try {
      const { response } = await askAnalistaMercado(historial.filter((m) => !m.error))
      setMensajes((prev) => [...prev, { role: 'assistant', content: response }])
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
    setMensajes([])
    setInput('')
    inputRef.current?.focus()
  }

  const fecha = formatearFecha(resumen?.actualizado)
  const vacia = mensajes.length === 0

  return (
    <div className="mx-auto flex h-[calc(100vh-4rem)] max-w-5xl flex-col">
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
        {!vacia && (
          <button
            onClick={nuevaConversacion}
            disabled={pensando}
            className="inline-flex shrink-0 items-center gap-2 rounded-xl border border-gray-300 bg-white px-4 py-2.5 text-base font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50 cursor-pointer"
          >
            <RotateCcw className="h-5 w-5" /> Nueva conversación
          </button>
        )}
      </div>

      {/* Conversación */}
      <div className="flex-1 overflow-y-auto rounded-2xl border border-gray-200 bg-white p-6">
        {vacia ? (
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
          disabled={pensando}
          placeholder="Escriba aquí su pregunta. Ej: ¿Cuánto cuesta un departamento en la Zona Dorada?"
          className="flex-1 rounded-xl border border-gray-300 bg-white px-5 py-4 text-base focus:border-transparent focus:outline-none focus:ring-2 focus:ring-emerald-400 disabled:bg-gray-50"
        />
        <button
          type="submit"
          disabled={!input.trim() || pensando}
          className="inline-flex items-center gap-2 rounded-xl bg-emerald-600 px-6 py-4 text-base font-semibold text-white hover:bg-emerald-700 disabled:bg-gray-300 cursor-pointer"
        >
          <Send className="h-5 w-5" /> Preguntar
        </button>
      </form>
    </div>
  )
}
