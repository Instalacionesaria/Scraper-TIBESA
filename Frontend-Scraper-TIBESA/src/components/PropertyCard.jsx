import { MapPin, DollarSign, Home, Sparkles, Star, Ruler, BedDouble } from 'lucide-react'

const typeLabels = {
  casa: 'Casa',
  departamento: 'Departamento',
  condominio: 'Condominio',
  terreno: 'Terreno',
  terreno_agricola: 'Terreno Agrícola',
  local_comercial: 'Local Comercial',
  bodega: 'Bodega',
  edificio: 'Edificio',
  lote: 'Lote',
  rancho: 'Rancho',
}

const typeColors = {
  casa: 'bg-blue-100 text-blue-700',
  departamento: 'bg-purple-100 text-purple-700',
  condominio: 'bg-indigo-100 text-indigo-700',
  terreno: 'bg-green-100 text-green-700',
  terreno_agricola: 'bg-lime-100 text-lime-700',
  local_comercial: 'bg-orange-100 text-orange-700',
  bodega: 'bg-amber-100 text-amber-700',
  edificio: 'bg-cyan-100 text-cyan-700',
  lote: 'bg-emerald-100 text-emerald-700',
  rancho: 'bg-yellow-100 text-yellow-700',
}

export default function PropertyCard({ property, index }) {
  const tipo = property.tipo_propiedad || 'N/A'
  const terreno = property.terreno || {}
  const construccion = property.construccion || {}
  const espacios = property.espacios_interiores || {}

  return (
    <div className="bg-white border border-gray-200 rounded-xl p-5 hover:shadow-md transition-shadow animate-in">
      {/* Header: index + tipo badge */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-400 font-mono">#{index}</span>
          <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${typeColors[tipo] || 'bg-gray-100 text-gray-600'}`}>
            {typeLabels[tipo] || tipo}
          </span>
          {property.procesado_con_ia && (
            <span className="inline-flex items-center gap-1 text-xs text-violet-600 bg-violet-50 px-2 py-0.5 rounded-full">
              <Sparkles className="w-3 h-3" /> IA
            </span>
          )}
        </div>
        <span className="text-sm font-bold text-green-700 bg-green-50 px-3 py-1 rounded-lg">
          {property.precio || 'N/A'}
        </span>
      </div>

      {/* Titulo */}
      <h3 className="font-semibold text-gray-900 text-sm mb-2 line-clamp-2">
        {property.titulo || 'Sin título'}
      </h3>

      {/* Ubicación */}
      {property.ubicacion && (
        <div className="flex items-center gap-1.5 text-xs text-gray-500 mb-3">
          <MapPin className="w-3 h-3 shrink-0" />
          <span className="line-clamp-1">{property.ubicacion}</span>
        </div>
      )}

      {/* Datos rápidos */}
      <div className="flex flex-wrap gap-2 mb-3">
        {terreno.metros_cuadrados && (
          <span className="inline-flex items-center gap-1 text-xs bg-gray-50 border border-gray-100 px-2 py-1 rounded">
            <Ruler className="w-3 h-3 text-gray-400" />
            Terreno: {terreno.metros_cuadrados} m²
          </span>
        )}
        {construccion.metros_cuadrados && (
          <span className="inline-flex items-center gap-1 text-xs bg-gray-50 border border-gray-100 px-2 py-1 rounded">
            <Home className="w-3 h-3 text-gray-400" />
            Const: {construccion.metros_cuadrados} m²
          </span>
        )}
        {espacios.recamaras && (
          <span className="inline-flex items-center gap-1 text-xs bg-gray-50 border border-gray-100 px-2 py-1 rounded">
            <BedDouble className="w-3 h-3 text-gray-400" />
            {espacios.recamaras} rec.
          </span>
        )}
        {property.num_imagenes > 0 && (
          <span className="text-xs bg-gray-50 border border-gray-100 px-2 py-1 rounded">
            {property.num_imagenes} imgs
          </span>
        )}
      </div>

      {/* Descripción comercial */}
      {property.descripcion_comercial && (
        <p className="text-xs text-gray-600 mb-3 line-clamp-2">
          {property.descripcion_comercial}
        </p>
      )}

      {/* Destacados */}
      {property.destacados_venta && property.destacados_venta.length > 0 && (
        <div className="space-y-1">
          {property.destacados_venta.slice(0, 2).map((dest, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs text-gray-500">
              <Star className="w-3 h-3 text-amber-400 shrink-0 mt-0.5" />
              <span className="line-clamp-1">{dest}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
