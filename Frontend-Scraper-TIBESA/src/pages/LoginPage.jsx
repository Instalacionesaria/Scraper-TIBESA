import { useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { Mail, Lock, LogIn, Loader2, AlertTriangle, Building2, Zap, CheckCircle2, Target } from 'lucide-react'
import { login } from '../lib/leadsApi'
import { saveCredentials } from '../lib/auth'

export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const from = location.state?.from?.pathname || '/leads'

  const [correo, setCorreo] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  const canSubmit = correo.trim() && password && !loading

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!canSubmit) return
    setLoading(true)
    setError('')
    try {
      const res = await login({ correo_electronico: correo.trim(), password })
      saveCredentials({
        correo_electronico: res.correo_electronico || correo.trim(),
        password,
        userId: res.userId || '',
      })
      navigate(from, { replace: true })
    } catch (err) {
      setError(err.message || 'No se pudo iniciar sesión.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex">
      {/* Panel izquierdo: formulario */}
      <div className="flex-1 flex items-center justify-center bg-gray-50 px-6 py-12">
        <div className="w-full max-w-md">
          <div className="text-center mb-10">
            <h1 className="text-3xl font-bold text-gray-900 mb-3">
              ¡Bienvenido al Sistema{' '}
              <span className="text-sky-600">TIBESA SCRAPER!</span>
            </h1>
            <p className="text-sm text-gray-500">
              Inicia sesión para acceder a tu sistema de captura de prospectos de clientes.
            </p>
          </div>

          <div className="bg-white border border-gray-200 rounded-2xl shadow-sm p-8">
            <div className="flex items-center gap-3 mb-6">
              <div className="w-10 h-10 bg-[#2c3e50] rounded-lg flex items-center justify-center p-1.5">
                <img src="/tibesa-logo.png" alt="TIBESA" className="w-full h-full object-contain" />
              </div>
              <div>
                <div className="text-sm font-bold text-gray-900 leading-tight">TIBESA SCRAPER</div>
                <div className="text-[11px] text-gray-500 tracking-wider">BIENES RAÍCES</div>
              </div>
            </div>

            <h2 className="text-lg font-semibold text-gray-900 mb-1">Accede a tu cuenta</h2>
            <p className="text-xs text-gray-500 mb-6">Conecta con tu sistema de captura de leads</p>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">Correo Electrónico</label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="email"
                    value={correo}
                    onChange={(e) => setCorreo(e.target.value)}
                    placeholder="tu@email.com"
                    disabled={loading}
                    autoComplete="email"
                    className="w-full pl-10 pr-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-400 focus:border-transparent disabled:bg-gray-50"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1.5">Contraseña de TIBESA SCRAPER</label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Ingresa tu contraseña"
                    disabled={loading}
                    autoComplete="current-password"
                    className="w-full pl-10 pr-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-sky-400 focus:border-transparent disabled:bg-gray-50"
                  />
                </div>
              </div>

              {error && (
                <div className="flex items-start gap-2 bg-red-50 border border-red-200 rounded-lg px-3 py-2 text-sm text-red-700">
                  <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-red-500" />
                  <span>{error}</span>
                </div>
              )}

              <button
                type="submit"
                disabled={!canSubmit}
                className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium text-white bg-sky-600 hover:bg-sky-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors cursor-pointer"
              >
                {loading ? (
                  <><Loader2 className="w-4 h-4 animate-spin" /> Iniciando sesión...</>
                ) : (
                  <><LogIn className="w-4 h-4" /> Iniciar Sesión</>
                )}
              </button>
            </form>
          </div>
        </div>
      </div>

      {/* Panel derecho: branding */}
      <div
        className="hidden lg:flex flex-1 items-center justify-center px-10 py-12 text-white relative overflow-hidden"
        style={{
          background:
            'radial-gradient(ellipse at top right, #3b5a7e 0%, #2c3e50 40%, #1a2530 100%)',
        }}
      >
        {/* Estrellas */}
        <div className="absolute inset-0 opacity-40 pointer-events-none"
          style={{
            backgroundImage:
              'radial-gradient(1px 1px at 10% 20%, white, transparent), radial-gradient(1px 1px at 30% 60%, white, transparent), radial-gradient(1px 1px at 60% 30%, white, transparent), radial-gradient(1.5px 1.5px at 80% 70%, white, transparent), radial-gradient(1px 1px at 50% 85%, white, transparent), radial-gradient(1px 1px at 20% 50%, white, transparent), radial-gradient(1px 1px at 75% 15%, white, transparent), radial-gradient(1px 1px at 90% 45%, white, transparent)',
          }}
        />

        <div className="relative max-w-md text-center">
          <div className="w-16 h-16 mx-auto mb-5 bg-[#2c3e50]/70 border border-white/10 rounded-xl flex items-center justify-center p-2">
            <img src="/tibesa-logo.png" alt="TIBESA" className="w-full h-full object-contain" />
          </div>

          <h2 className="text-2xl font-bold mb-1 tracking-wide">TIBESA SCRAPER</h2>
          <p className="text-[11px] tracking-[4px] text-white/50 mb-8">BIENES RAÍCES</p>

          <h3 className="text-xl font-semibold mb-4 leading-snug">
            Captura prospectos de clientes<br />con nuestro sistema inteligente
          </h3>

          <p className="text-sm text-white/70 bg-white/5 border border-white/10 rounded-xl px-5 py-4 mb-8">
            Encuentra y captura leads de calidad para tu negocio inmobiliario. Automatiza la
            búsqueda de prospectos y aumenta tus oportunidades de venta.
          </p>

          <div className="flex items-center justify-center gap-3 text-xs">
            <span className="inline-flex items-center gap-1.5 bg-white/10 border border-white/15 rounded-full px-3 py-1.5">
              <Zap className="w-3.5 h-3.5" /> Rápido
            </span>
            <span className="inline-flex items-center gap-1.5 bg-white/10 border border-white/15 rounded-full px-3 py-1.5">
              <Target className="w-3.5 h-3.5" /> Sencillo
            </span>
            <span className="inline-flex items-center gap-1.5 bg-white/10 border border-white/15 rounded-full px-3 py-1.5">
              <CheckCircle2 className="w-3.5 h-3.5" /> Efectivo
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}
