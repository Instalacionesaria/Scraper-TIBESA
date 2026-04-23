import { Home, MapPin, DollarSign, TrendingUp, Building2, Ruler } from 'lucide-react'

function parsePrice(priceStr) {
  if (!priceStr) return null
  const cleaned = priceStr.replace(/[^0-9.]/g, '')
  const num = parseFloat(cleaned)
  return isNaN(num) ? null : num
}

function formatPrice(num) {
  if (!num) return 'N/A'
  return '$' + num.toLocaleString('es-MX') + ' MXN'
}

export default function SummaryPanel({ properties }) {
  if (!properties || properties.length === 0) return null

  // Calcular estadísticas
  const total = properties.length

  // Por tipo
  const byType = {}
  properties.forEach(p => {
    const tipo = p.tipo_propiedad || 'sin_clasificar'
    byType[tipo] = (byType[tipo] || 0) + 1
  })

  // Precios
  const prices = properties.map(p => parsePrice(p.precio)).filter(Boolean)
  const avgPrice = prices.length > 0 ? prices.reduce((a, b) => a + b, 0) / prices.length : null
  const minPrice = prices.length > 0 ? Math.min(...prices) : null
  const maxPrice = prices.length > 0 ? Math.max(...prices) : null

  // Por ubicación
  const byLocation = {}
  properties.forEach(p => {
    if (!p.ubicacion) return
    // Extraer zona principal (primera parte antes de la coma)
    const zona = p.ubicacion.split(',')[0].trim().toUpperCase()
    byLocation[zona] = (byLocation[zona] || 0) + 1
  })
  const topLocations = Object.entries(byLocation)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)

  const typeLabels = {
    casa: 'Casas',
    departamento: 'Departamentos',
    condominio: 'Condominios',
    terreno: 'Terrenos',
    terreno_agricola: 'Terrenos Agrícolas',
    local_comercial: 'Locales Comerciales',
    bodega: 'Bodegas',
    edificio: 'Edificios',
    lote: 'Lotes',
    rancho: 'Ranchos',
    sin_clasificar: 'Sin clasificar',
  }

  const typeColors = {
    casa: 'bg-blue-500',
    departamento: 'bg-purple-500',
    condominio: 'bg-indigo-500',
    terreno: 'bg-green-500',
    terreno_agricola: 'bg-lime-500',
    local_comercial: 'bg-orange-500',
    bodega: 'bg-amber-500',
    edificio: 'bg-cyan-500',
    lote: 'bg-emerald-500',
    rancho: 'bg-yellow-500',
    sin_clasificar: 'bg-gray-400',
  }

  const conIA = properties.filter(p => p.procesado_con_ia).length

  return (
    <div className="mb-8 bg-white border border-gray-200 rounded-xl p-6">
      <h2 className="text-lg font-bold text-gray-800 mb-5 flex items-center gap-2">
        <TrendingUp className="w-5 h-5 text-[#2c3e50]" />
        Resumen General
      </h2>

      {/* KPI cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <div className="bg-gray-50 rounded-lg p-4 text-center">
          <Building2 className="w-5 h-5 text-gray-400 mx-auto mb-1" />
          <div className="text-2xl font-bold text-gray-800">{total}</div>
          <div className="text-xs text-gray-500">Propiedades</div>
        </div>
        <div className="bg-green-50 rounded-lg p-4 text-center">
          <DollarSign className="w-5 h-5 text-green-500 mx-auto mb-1" />
          <div className="text-lg font-bold text-green-700">{formatPrice(avgPrice)}</div>
          <div className="text-xs text-green-600">Precio Promedio</div>
        </div>
        <div className="bg-blue-50 rounded-lg p-4 text-center">
          <DollarSign className="w-5 h-5 text-blue-500 mx-auto mb-1" />
          <div className="text-lg font-bold text-blue-700">{formatPrice(minPrice)}</div>
          <div className="text-xs text-blue-600">Precio Mínimo</div>
        </div>
        <div className="bg-violet-50 rounded-lg p-4 text-center">
          <DollarSign className="w-5 h-5 text-violet-500 mx-auto mb-1" />
          <div className="text-lg font-bold text-violet-700">{formatPrice(maxPrice)}</div>
          <div className="text-xs text-violet-600">Precio Máximo</div>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* By type */}
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
            <Home className="w-4 h-4" /> Por Tipo de Propiedad
          </h3>
          <div className="space-y-2">
            {Object.entries(byType)
              .sort((a, b) => b[1] - a[1])
              .map(([tipo, count]) => (
                <div key={tipo} className="flex items-center gap-2">
                  <div className={`w-3 h-3 rounded-full ${typeColors[tipo] || 'bg-gray-400'}`} />
                  <span className="text-sm text-gray-700 flex-1">{typeLabels[tipo] || tipo}</span>
                  <span className="text-sm font-semibold text-gray-800">{count}</span>
                  <div className="w-20 bg-gray-100 rounded-full h-2">
                    <div
                      className={`h-2 rounded-full ${typeColors[tipo] || 'bg-gray-400'}`}
                      style={{ width: `${(count / total) * 100}%` }}
                    />
                  </div>
                </div>
              ))}
          </div>
        </div>

        {/* By location */}
        <div>
          <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-1.5">
            <MapPin className="w-4 h-4" /> Principales Zonas
          </h3>
          <div className="space-y-2">
            {topLocations.map(([zona, count]) => (
              <div key={zona} className="flex items-center gap-2">
                <span className="text-sm text-gray-700 flex-1 truncate">{zona}</span>
                <span className="text-sm font-semibold text-gray-800">{count}</span>
                <div className="w-20 bg-gray-100 rounded-full h-2">
                  <div
                    className="h-2 rounded-full bg-sky-500"
                    style={{ width: `${(count / total) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Footer note */}
      <div className="mt-5 pt-4 border-t border-gray-100 text-xs text-gray-400 text-center">
        {conIA} de {total} propiedades analizadas con IA
      </div>
    </div>
  )
}
