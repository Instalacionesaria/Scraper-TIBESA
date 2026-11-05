import { useState, useRef, useEffect } from 'react'
import { Sparkles, Send, Loader2, Bot, User, CheckCircle2 } from 'lucide-react'

// Chat IA genérico que llena un formulario de búsqueda.
//
// Props:
//   ask({ messages, current })  → llama al endpoint del asistente; devuelve { respuesta, campos, listo }
//   mapCampos(campos)           → convierte los `campos` del backend en { claveDelFormulario: valor }
//   labels                      → { claveDelFormulario: 'Etiqueta visible' } para los chips
//   current                     → valores actuales del formulario
//   onApply(applied)            → actualiza el formulario con los campos sugeridos
//   greeting, suggestions, placeholder, disabled
export default function FormAssistant({
  ask,
  mapCampos,
  labels,
  current,
  onApply,
  greeting,
  suggestions = [],
  placeholder = 'Escribe lo que buscas…',
  disabled = false,
}) {
  const [messages, setMessages] = useState([{ role: 'assistant', content: greeting, local: true }])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const scrollRef = useRef(null)

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, loading])

  const sendMessage = async (text) => {
    const content = (text ?? input).trim()
    if (!content || loading || disabled) return

    const next = [...messages, { role: 'user', content }]
    setMessages(next)
    setInput('')
    setLoading(true)

    try {
      // El saludo es local; no lo mandamos al LLM.
      const history = next.filter((m) => !m.local).map(({ role, content }) => ({ role, content }))
      const res = await ask({ messages: history, current })

      const applied = mapCampos(res.campos || {})
      if (Object.keys(applied).length) onApply(applied)

      setMessages((prev) => [...prev, { role: 'assistant', content: res.respuesta, applied }])
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `No pude responder ahora (${e.message}). Intenta de nuevo en un momento.` },
      ])
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  const formatValue = (v) => {
    if (v === '') return '(vacío)'
    if (typeof v === 'boolean') return v ? 'Sí' : 'No'
    return String(v)
  }

  const onlyGreeting = messages.length === 1

  return (
    <div className="mt-6 bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="px-6 py-4 border-b border-gray-100 flex items-center gap-2">
        <Sparkles className="w-5 h-5 text-[#0a66c2]" />
        <div>
          <h2 className="text-lg font-semibold text-gray-800 leading-tight">Asistente IA</h2>
          <p className="text-xs text-gray-500">Escribe en español lo que buscas y lleno los campos por ti</p>
        </div>
      </div>

      <div ref={scrollRef} className="h-72 overflow-y-auto p-4 space-y-3 bg-gray-50/60">
        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'assistant' && (
              <div className="w-7 h-7 rounded-full bg-sky-100 flex items-center justify-center shrink-0 mt-0.5">
                <Bot className="w-4 h-4 text-[#0a66c2]" />
              </div>
            )}
            <div className="max-w-[80%]">
              <div
                className={`px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap ${
                  msg.role === 'user'
                    ? 'bg-[#2c3e50] text-white rounded-br-md'
                    : 'bg-white border border-gray-200 text-gray-800 rounded-bl-md'
                }`}
              >
                {msg.content}
              </div>
              {msg.applied && Object.keys(msg.applied).length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1.5">
                  {Object.entries(msg.applied).map(([k, v]) => (
                    <span
                      key={k}
                      className="inline-flex items-center gap-1 text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 px-2 py-0.5 rounded-full"
                    >
                      <CheckCircle2 className="w-3 h-3" />
                      {labels[k] || k}: {formatValue(v)}
                    </span>
                  ))}
                </div>
              )}
            </div>
            {msg.role === 'user' && (
              <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center shrink-0 mt-0.5">
                <User className="w-4 h-4 text-gray-500" />
              </div>
            )}
          </div>
        ))}

        {onlyGreeting && suggestions.length > 0 && (
          <div className="flex flex-wrap gap-2 pl-9">
            {suggestions.map((s) => (
              <button
                key={s}
                onClick={() => sendMessage(s)}
                disabled={disabled}
                className="text-xs bg-sky-50 text-[#0a66c2] border border-sky-100 px-3 py-1.5 rounded-full hover:bg-sky-100 transition-colors cursor-pointer disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {loading && (
          <div className="flex gap-2 items-center">
            <div className="w-7 h-7 rounded-full bg-sky-100 flex items-center justify-center shrink-0">
              <Bot className="w-4 h-4 text-[#0a66c2]" />
            </div>
            <div className="bg-white border border-gray-200 px-4 py-2.5 rounded-2xl rounded-bl-md">
              <Loader2 className="w-4 h-4 animate-spin text-[#0a66c2]" />
            </div>
          </div>
        )}
      </div>

      <div className="border-t border-gray-200 p-3 flex gap-2">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={loading || disabled}
          placeholder={disabled ? 'Espera a que termine el scrapeo…' : placeholder}
          className="flex-1 px-4 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-400 focus:border-transparent disabled:bg-gray-50 disabled:text-gray-400"
        />
        <button
          onClick={() => sendMessage()}
          disabled={!input.trim() || loading || disabled}
          className="px-4 py-2 bg-[#0a66c2] text-white rounded-lg hover:bg-[#084c95] disabled:bg-gray-200 disabled:text-gray-400 transition-colors cursor-pointer"
          aria-label="Enviar"
        >
          <Send className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}
