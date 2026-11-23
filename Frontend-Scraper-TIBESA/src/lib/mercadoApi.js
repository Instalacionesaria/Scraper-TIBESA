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

// Informe de Mercado en PDF (se guarda también en "Resultados").
// → { filename, titulo, subtitulo, created_at, size_bytes, download_url }
export function generarInforme({ threadId, usuario }) {
  return request('/api/mercado/informe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ thread_id: threadId, usuario }),
  })
}

// → { count, informes: [{ filename, titulo, subtitulo, preguntas, created_at, size_bytes, download_url }] }
export function listarInformes() {
  return request('/api/mercado/informes')
}

export function urlDescarga(downloadUrl) {
  return `${API_BASE}${downloadUrl}`
}

// Descarga el PDF sin salir de la página (el backend responde con Content-Disposition: attachment).
export function descargarArchivo(downloadUrl) {
  const a = document.createElement('a')
  a.href = urlDescarga(downloadUrl)
  a.rel = 'noopener'
  document.body.appendChild(a)
  a.click()
  a.remove()
}
