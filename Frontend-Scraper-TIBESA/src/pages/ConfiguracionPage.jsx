import { useState, useEffect } from 'react'
import { Settings, Key, CheckCircle2 } from 'lucide-react'
import { getCredentials, saveCredentials, clearCredentials } from '../lib/auth'

export default function ConfiguracionPage() {
  const [correo, setCorreo] = useState('')
  const [password, setPassword] = useState('')
  const [saved, setSaved] = useState(false)
  const [hasSavedCreds, setHasSavedCreds] = useState(false)

  useEffect(() => {
    const c = getCredentials()
    if (c) {
      setCorreo(c.correo_electronico || '')
      setPassword(c.password || '')
      setHasSavedCreds(true)
    }
  }, [])

  const handleSave = (e) => {
    e.preventDefault()
    if (!correo.trim() || !password.trim()) return
    saveCredentials({ correo_electronico: correo, password })
    setHasSavedCreds(true)
    setSaved(true)
    setTimeout(() => setSaved(false), 2500)
  }

  const handleClear = () => {
    clearCredentials()
    setCorreo('')
    setPassword('')
    setHasSavedCreds(false)
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
          <Settings className="w-7 h-7 text-[#2c3e50]" />
          Configuración
        </h1>
        <p className="text-gray-500 mt-1">Ajusta los parámetros del scraper y tus credenciales TIBESA</p>
      </div>

      <div className="space-y-6">
        {/* Credenciales TIBESA */}
        <form onSubmit={handleSave} className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="font-semibold text-gray-800 mb-1 flex items-center gap-2">
            <Key className="w-4 h-4 text-[#2c3e50]" />
            Credenciales TIBESA
          </h3>
          <p className="text-xs text-gray-500 mb-4">
            Necesarias para autenticar las búsquedas de leads y envíos al CRM. Se guardan sólo en este navegador.
          </p>

          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium text-gray-700">Correo electrónico</label>
              <input
                type="email"
                value={correo}
                onChange={(e) => setCorreo(e.target.value)}
                placeholder="tu-correo@empresa.com"
                required
                className="mt-1 block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-300"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-gray-700">Password</label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                required
                className="mt-1 block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-300"
              />
            </div>

            <div className="flex items-center gap-3">
              <button
                type="submit"
                className="px-4 py-2 rounded-lg text-sm font-medium text-white bg-[#2c3e50] hover:bg-[#34495e] cursor-pointer transition-colors"
              >
                Guardar credenciales
              </button>
              {hasSavedCreds && (
                <button
                  type="button"
                  onClick={handleClear}
                  className="px-4 py-2 rounded-lg text-sm font-medium text-gray-600 hover:bg-gray-100 cursor-pointer transition-colors"
                >
                  Borrar
                </button>
              )}
              {saved && (
                <span className="inline-flex items-center gap-1 text-sm text-green-700">
                  <CheckCircle2 className="w-4 h-4" /> Guardado
                </span>
              )}
            </div>
          </div>
        </form>

        {/* Scraper settings (cosméticos por ahora) */}
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="font-semibold text-gray-800 mb-4">Scraper</h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-700">Modo Headless</p>
                <p className="text-xs text-gray-400">Ejecutar navegador en segundo plano</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" defaultChecked className="sr-only peer" />
                <div className="w-11 h-6 bg-gray-200 peer-focus:ring-2 peer-focus:ring-sky-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:bg-[#2c3e50] after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all" />
              </label>
            </div>
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-700">Descargar Imágenes</p>
                <p className="text-xs text-gray-400">Guardar imágenes de cada propiedad</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" defaultChecked className="sr-only peer" />
                <div className="w-11 h-6 bg-gray-200 peer-focus:ring-2 peer-focus:ring-sky-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:bg-[#2c3e50] after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all" />
              </label>
            </div>
          </div>
        </div>

        {/* AI settings */}
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="font-semibold text-gray-800 mb-4">Agente IA</h3>
          <div>
            <label className="text-sm font-medium text-gray-700">Modelo</label>
            <select className="mt-1 block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-300">
              <option>gpt-5-mini</option>
              <option>gpt-4o-mini</option>
              <option>gpt-4o</option>
            </select>
          </div>
        </div>
      </div>
    </div>
  )
}
