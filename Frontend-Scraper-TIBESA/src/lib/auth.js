// Credenciales del usuario (se guardan en localStorage del navegador).
// Las necesitamos para autenticar contra el backend de leads de TIBESA.

const KEY = 'tibesa_credentials'

export function getCredentials() {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const parsed = JSON.parse(raw)
    if (!parsed.correo_electronico) return null
    return parsed
  } catch {
    return null
  }
}

export function saveCredentials({ correo_electronico, password, userId }) {
  localStorage.setItem(
    KEY,
    JSON.stringify({
      correo_electronico: correo_electronico?.trim() || '',
      password: password || '',
      userId: userId || '',
    })
  )
}

export function clearCredentials() {
  localStorage.removeItem(KEY)
}

export function hasCredentials() {
  const c = getCredentials()
  return !!(c && c.correo_electronico && c.password)
}
