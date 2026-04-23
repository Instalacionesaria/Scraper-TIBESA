import { useState, useRef, useEffect } from 'react'
import { MessageCircle, Send, Loader2, Sparkles, User, Bot, ChevronDown, ChevronUp } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

const SUGGESTIONS = [
  '¿Cuántas casas hay y cuál es el precio promedio?',
  '¿Cuál es la propiedad más barata?',
  '¿Qué propiedades hay en la zona de Sonterra?',
  '¿Qué terrenos están disponibles?',
  'Dame un resumen de las propiedades scrapeadas',
]

export default function ChatPanel({ properties }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [isOpen, setIsOpen] = useState(false)
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  useEffect(() => {
    if (isOpen) inputRef.current?.focus()
  }, [isOpen])

  const sendMessage = async (text) => {
    const userMsg = text || input.trim()
    if (!userMsg) return

    setMessages(prev => [...prev, { role: 'user', content: userMsg }])
    setInput('')
    setLoading(true)

    try {
      // Preparar propiedades resumidas para el contexto
      const propsForChat = properties.map(p => ({
        titulo: p.titulo,
        precio: p.precio,
        ubicacion: p.ubicacion,
        tipo_propiedad: p.tipo_propiedad,
        descripcion_comercial: p.descripcion_comercial,
        terreno: p.terreno,
        construccion: p.construccion,
        espacios_interiores: p.espacios_interiores,
      }))

      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMsg, properties: propsForChat }),
      })

      const data = await res.json()
      setMessages(prev => [...prev, { role: 'assistant', content: data.response || data.detail || 'Error al procesar' }])
    } catch (err) {
      setMessages(prev => [...prev, { role: 'assistant', content: 'No se pudo conectar al servidor. Verifica que el backend esté corriendo.' }])
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

  const hasProperties = properties.length > 0

  return (
    <div className="mb-6">
      {/* Toggle button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`w-full flex items-center justify-between px-5 py-3 rounded-xl border transition-all cursor-pointer ${
          isOpen
            ? 'bg-violet-50 border-violet-200 text-violet-800'
            : 'bg-white border-gray-200 text-gray-700 hover:border-violet-200 hover:bg-violet-50/50'
        }`}
      >
        <div className="flex items-center gap-2">
          <MessageCircle className="w-5 h-5" />
          <span className="font-medium text-sm">Chat con IA sobre propiedades scrapeadas</span>
          {!hasProperties && (
            <span className="text-xs text-gray-400">(scrapea primero para consultar)</span>
          )}
        </div>
        {isOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
      </button>

      {/* Chat body */}
      {isOpen && (
        <div className="mt-2 border border-violet-200 rounded-xl bg-white overflow-hidden">
          {/* Messages area */}
          <div className="h-80 overflow-y-auto p-4 space-y-3 bg-gray-50/50">
            {messages.length === 0 && (
              <div className="text-center py-8">
                <Sparkles className="w-8 h-8 text-violet-300 mx-auto mb-3" />
                <p className="text-sm text-gray-500 mb-4">
                  {hasProperties
                    ? `Pregunta lo que quieras sobre las ${properties.length} propiedades scrapeadas`
                    : 'Ejecuta un scraping primero para poder consultar los datos'}
                </p>
                {hasProperties && (
                  <div className="flex flex-wrap justify-center gap-2">
                    {SUGGESTIONS.map((s, i) => (
                      <button
                        key={i}
                        onClick={() => sendMessage(s)}
                        className="text-xs bg-violet-50 text-violet-700 border border-violet-100 px-3 py-1.5 rounded-full hover:bg-violet-100 transition-colors cursor-pointer"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}

            {messages.map((msg, i) => (
              <div key={i} className={`flex gap-2 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                {msg.role === 'assistant' && (
                  <div className="w-7 h-7 rounded-full bg-violet-100 flex items-center justify-center shrink-0 mt-0.5">
                    <Bot className="w-4 h-4 text-violet-600" />
                  </div>
                )}
                <div
                  className={`max-w-[80%] px-4 py-2.5 rounded-2xl text-sm whitespace-pre-wrap ${
                    msg.role === 'user'
                      ? 'bg-[#2c3e50] text-white rounded-br-md'
                      : 'bg-white border border-gray-200 text-gray-800 rounded-bl-md'
                  }`}
                >
                  {msg.content}
                </div>
                {msg.role === 'user' && (
                  <div className="w-7 h-7 rounded-full bg-gray-200 flex items-center justify-center shrink-0 mt-0.5">
                    <User className="w-4 h-4 text-gray-500" />
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex gap-2 items-center">
                <div className="w-7 h-7 rounded-full bg-violet-100 flex items-center justify-center shrink-0">
                  <Bot className="w-4 h-4 text-violet-600" />
                </div>
                <div className="bg-white border border-gray-200 px-4 py-2.5 rounded-2xl rounded-bl-md">
                  <Loader2 className="w-4 h-4 animate-spin text-violet-500" />
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          <div className="border-t border-gray-200 p-3 flex gap-2">
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={!hasProperties || loading}
              placeholder={hasProperties ? 'Pregunta sobre las propiedades...' : 'Scrapea propiedades primero...'}
              className="flex-1 px-4 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-violet-300 disabled:bg-gray-50 disabled:text-gray-400"
            />
            <button
              onClick={() => sendMessage()}
              disabled={!input.trim() || loading || !hasProperties}
              className="px-4 py-2 bg-violet-600 text-white rounded-lg hover:bg-violet-700 disabled:bg-gray-200 disabled:text-gray-400 transition-colors cursor-pointer"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
