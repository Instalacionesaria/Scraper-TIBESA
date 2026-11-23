import FormAssistant from './FormAssistant'
import { askFacebookAssistant } from '../lib/leadsApi'

const LABELS = { busqueda: 'Búsqueda', pais: 'País', etiqueta: 'Etiqueta CRM' }

const SUGGESTIONS = [
  'Inmobiliarias que anuncian en México',
  'Desarrolladores con preventas en Mazatlán',
  'Agentes de real estate en Estados Unidos',
]

function mapCampos(c) {
  const applied = {}
  if (c.url_biblioteca) {
    applied.urlBiblioteca = c.url_biblioteca
    if (c.palabra_clave) applied.busqueda = c.palabra_clave
    if (c.pais) applied.pais = c.pais === 'ALL' ? 'Todos' : c.pais
  }
  if (c.etiqueta) applied.etiqueta = c.etiqueta
  return applied
}

// Chat IA que arma la URL de la Biblioteca de Anuncios de Facebook y la etiqueta del CRM.
export default function FacebookAssistant({ current, onApply, disabled = false }) {
  return (
    <FormAssistant
      ask={askFacebookAssistant}
      mapCampos={mapCampos}
      labels={LABELS}
      hiddenKeys={['urlBiblioteca']}
      current={current}
      onApply={onApply}
      disabled={disabled}
      greeting="¡Hola! Dígame qué tipo de negocios quiere encontrar entre los que anuncian en Facebook (por ejemplo, inmobiliarias en México) y yo armo la búsqueda por usted."
      suggestions={SUGGESTIONS}
      placeholder="Ej: Inmobiliarias que anuncian en Mazatlán"
    />
  )
}
