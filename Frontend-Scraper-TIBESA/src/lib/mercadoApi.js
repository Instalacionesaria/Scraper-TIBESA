// API del Analista de Mercado (agente sobre TODAS las propiedades guardadas).
// El histórico de cada conversación lo guarda el backend (checkpointer) bajo un thread_id.
const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

async function request(path, options) {
  const res = await fetch(`${API_BASE}${path}`, options)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || data.message || `Error ${res.status}`)
  return data
}

const q = (usuario) => (usuario ? `?usuario=${encodeURIComponent(usuario)}` : '')

// { propiedades, portales, actualizado, historico: { modo, detalle } }
export function getResumenMercado() {
  return request('/api/mercado/resumen')
}

// → { graficos: [...] } panel general antes de preguntar
export function getPanorama() {
  return request('/api/mercado/panorama')
}

// → { response, graficos, thread_id }
export function askAnalistaMercado({ threadId, mensaje, usuario }) {
  return request('/api/mercado/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ thread_id: threadId, mensaje, usuario }),
  })
}

// → { conversaciones: [{ thread_id, actualizado, titulo, preguntas }] }
export function listarConversaciones(usuario) {
  return request(`/api/mercado/conversaciones${q(usuario)}`)
}

// → { thread_id, mensajes: [{ role, content }] }
export function getConversacion(threadId, usuario) {
  return request(`/api/mercado/conversaciones/${encodeURIComponent(threadId)}${q(usuario)}`)
}

export function borrarConversacion(threadId, usuario) {
  return request(`/api/mercado/conversaciones/${encodeURIComponent(threadId)}${q(usuario)}`, { method: 'DELETE' })
}
