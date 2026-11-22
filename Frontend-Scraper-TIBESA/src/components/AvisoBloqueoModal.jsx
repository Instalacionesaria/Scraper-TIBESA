import { useEffect } from 'react'
import { ShieldAlert, Database, X } from 'lucide-react'

/**
 * Modal amigable que explica que un portal bloqueó la actualización automática
 * y ofrece seguir trabajando con lo ya guardado.
 *
 * Pensado para un usuario no técnico: texto grande, lenguaje simple y una sola
 * acción principal (ver lo guardado).
 */
export default function AvisoBloqueoModal({
  sitio,              // nombre visible del portal, p. ej. "Trovit"
  totalGuardadas,     // número de propiedades guardadas (0 / undefined si no hay)
  fechaGuardado,      // texto ya formateado de la última actualización, o null
  onVerGuardado,      // abre las propiedades guardadas
  onIntentarIgual,    // opcional: lanza el scrapeo de todos modos
  onCerrar,
}) {
  // Cerrar con la tecla Escape
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onCerrar() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onCerrar])

  const hayGuardado = totalGuardadas > 0

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onCerrar}
      role="dialog"
      aria-modal="true"
      aria-labelledby="aviso-bloqueo-titulo"
    >
      <div
        className="relative w-full max-w-lg rounded-2xl bg-white p-7 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onCerrar}
          aria-label="Cerrar"
          className="absolute right-4 top-4 rounded-full p-1.5 text-gray-400 hover:bg-gray-100 hover:text-gray-600 cursor-pointer"
        >
          <X className="h-5 w-5" />
        </button>

        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-amber-100">
          <ShieldAlert className="h-7 w-7 text-amber-600" />
        </div>

        <h2 id="aviso-bloqueo-titulo" className="mb-3 text-xl font-bold text-gray-900">
          {sitio} no nos deja actualizar sus datos
        </h2>

        <p className="mb-4 text-base leading-relaxed text-gray-700">
          La página de {sitio} está bloqueando el acceso de nuestro sistema, por eso
          por ahora no se pueden traer propiedades nuevas. No es una falla de la
          aplicación.
        </p>

        {hayGuardado ? (
          <div className="mb-6 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-base leading-relaxed text-emerald-900">
            <strong>La buena noticia:</strong> tiene{' '}
            <strong>{totalGuardadas} propiedades guardadas</strong>
            {fechaGuardado && <> (actualizadas el {fechaGuardado})</>}. Puede seguir
            consultándolas y trabajando con ellas con normalidad.
          </div>
        ) : (
          <p className="mb-6 text-base leading-relaxed text-gray-700">
            Todavía no hay propiedades guardadas de este portal.
          </p>
        )}

        <div className="flex flex-col gap-3">
          {hayGuardado && (
            <button
              onClick={onVerGuardado}
              autoFocus
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-emerald-600 px-5 py-3.5 text-base font-semibold text-white shadow-sm hover:bg-emerald-700 cursor-pointer"
            >
              <Database className="h-5 w-5" />
              Ver las {totalGuardadas} propiedades guardadas
            </button>
          )}
          <button
            onClick={onCerrar}
            autoFocus={!hayGuardado}
            className="w-full rounded-xl border border-gray-300 bg-white px-5 py-3 text-base font-medium text-gray-700 hover:bg-gray-50 cursor-pointer"
          >
            Entendido
          </button>
          {onIntentarIgual && (
            <button
              onClick={onIntentarIgual}
              className="mt-1 text-sm text-gray-400 underline hover:text-gray-600 cursor-pointer"
            >
              Intentar actualizar de todos modos
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
