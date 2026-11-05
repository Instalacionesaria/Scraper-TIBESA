import FormAssistant from './FormAssistant'
import { askBusquedaLeadsAssistant } from '../lib/leadsApi'

const LABELS = { tipoNegocio: 'Tipo de Negocio', localizacion: 'Localización', enriquecer: 'Datos Premium' }

const SUGGESTIONS = [
  'Inmobiliarias en la Zona Dorada de Mazatlán',
  'Notarías en Mazatlán con sus correos',
  'Constructoras en Culiacán',
]

function mapCampos(c) {
  const applied = {}
  if (c.tipo_negocio) applied.tipoNegocio = c.tipo_negocio
  if (c.localizacion) applied.localizacion = c.localizacion
  if (typeof c.enriquecer === 'boolean') applied.enriquecer = c.enriquecer
  return applied
}

// Chat IA que llena el formulario de Búsqueda de Leads (Google Maps).
export default function BusquedaLeadsAssistant({ current, onApply, disabled = false }) {
  return (
    <FormAssistant
      ask={askBusquedaLeadsAssistant}
      mapCampos={mapCampos}
      labels={LABELS}
      current={current}
      onApply={onApply}
      disabled={disabled}
      greeting="¡Hola! Dime qué tipo de negocios quieres encontrar en Google Maps y en qué zona o ciudad, y yo lleno los campos por ti."
      suggestions={SUGGESTIONS}
      placeholder="Ej: Busco inmobiliarias en Mazatlán"
    />
  )
}
