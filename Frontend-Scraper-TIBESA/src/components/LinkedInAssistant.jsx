import FormAssistant from './FormAssistant'
import { askLinkedInAssistant } from '../lib/leadsApi'

const LABELS = { jobTitle: 'Job Title', country: 'Country', state: 'State', numberOfLeads: 'Leads' }

const SUGGESTIONS = [
  'Quiero agentes inmobiliarios de California',
  'Busco inversionistas en bienes raíces de Canadá',
  'Corredores inmobiliarios en Texas, unos 200',
]

function mapCampos(c) {
  const applied = {}
  if (c.job_title) applied.jobTitle = c.job_title
  if (c.country) applied.country = c.country
  if (c.state !== null && c.state !== undefined) applied.state = c.state
  if (c.number_of_leads) applied.numberOfLeads = c.number_of_leads
  return applied
}

// Chat IA que llena el formulario del Scraper de LinkedIn.
export default function LinkedInAssistant({ current, onApply, disabled = false }) {
  return (
    <FormAssistant
      ask={askLinkedInAssistant}
      mapCampos={mapCampos}
      labels={LABELS}
      current={current}
      onApply={onApply}
      disabled={disabled}
      greeting="¡Hola! Cuéntame qué tipo de personas quieres encontrar en LinkedIn (a qué se dedican y en qué país o estado) y yo lleno los campos por ti."
      suggestions={SUGGESTIONS}
      placeholder="Ej: Quiero corredores inmobiliarios de Arizona"
    />
  )
}
