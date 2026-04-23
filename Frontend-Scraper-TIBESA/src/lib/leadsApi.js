// Cliente para los endpoints /api/leads/* del backend.

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

async function post(path, body) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const msg = data.detail || data.message || `Error ${res.status}`
    throw new Error(msg)
  }
  return data
}

async function get(path) {
  const res = await fetch(`${API_BASE}${path}`)
  const data = await res.json().catch(() => ({}))
  if (!res.ok) {
    const msg = data.detail || data.message || `Error ${res.status}`
    throw new Error(msg)
  }
  return data
}

// ---------- Endpoints ----------

export function startGooglePlaces({ businessType, location, getEmails, credentials }) {
  return post('/api/leads/google-places/start', {
    businessType,
    location,
    getEmails,
    timestamp: new Date().toISOString(),
    userId: credentials.userId || '',
    correo_electronico: credentials.correo_electronico,
    password: credentials.password,
  })
}

export function startFacebookAds({ url, credentials }) {
  return post('/api/leads/facebook/ads/start', {
    url,
    userId: credentials.userId || null,
    correo_electronico: credentials.correo_electronico,
    timestamp: new Date().toISOString(),
  })
}

export function startFacebookPages({ pages, credentials }) {
  return post('/api/leads/facebook/pages/start', {
    pages,
    userId: credentials.userId || null,
    correo_electronico: credentials.correo_electronico,
    timestamp: new Date().toISOString(),
  })
}

export function sendToCrm({ jobId, etiqueta, credentials }) {
  return post('/api/leads/crm/send', {
    job_id: jobId,
    etiqueta,
    correo_electronico: credentials.correo_electronico,
  })
}

export function getJob(jobId) {
  return get(`/api/leads/jobs/${jobId}`)
}

export function cancelJob(jobId) {
  return post(`/api/leads/jobs/${jobId}/cancel`, {})
}

// ---------- Polling helper ----------

// Hace polling de un job hasta que termine (COMPLETED / FAILED / CANCELLED).
// onUpdate(job) se llama en cada tick.
export async function pollJobUntilDone(jobId, { onUpdate, intervalMs = 3000, timeoutMs = 10 * 60 * 1000 } = {}) {
  const start = Date.now()
  while (true) {
    const job = await getJob(jobId)
    if (onUpdate) onUpdate(job)

    if (job.status === 'COMPLETED' || job.status === 'FAILED' || job.status === 'CANCELLED') {
      return job
    }
    if (Date.now() - start > timeoutMs) {
      throw new Error('Timeout esperando el resultado del scrapeo')
    }
    await new Promise((r) => setTimeout(r, intervalMs))
  }
}
