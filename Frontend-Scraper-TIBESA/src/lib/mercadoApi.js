// API del Analista de Mercado (agente sobre TODAS las propiedades guardadas).
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

async function request(path, options) {
  const res = await fetch(`${API_BASE}${path}`, options)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || data.message || `Error ${res.status}`)
  return data
}

// { propiedades, portales, actualizado }
export function getResumenMercado() {
  return request('/api/mercado/resumen')
}

// messages: [{ role: 'user'|'assistant', content }] → { response }
export function askAnalistaMercado(messages) {
  return request('/api/mercado/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages }),
  })
}
