import { Settings } from 'lucide-react'

export default function ConfiguracionPage() {
  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 flex items-center gap-3">
          <Settings className="w-7 h-7 text-[#2c3e50]" />
          Configuración
        </h1>
        <p className="text-gray-500 mt-1">
          Ajusta los parámetros del scraper y el procesamiento IA
        </p>
      </div>

      <div className="space-y-6">
        {/* Scraper settings */}
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
            <div>
              <label className="text-sm font-medium text-gray-700">Delay entre requests (seg)</label>
              <input
                type="number"
                defaultValue={2}
                min={0.5}
                max={10}
                step={0.5}
                className="mt-1 block w-full border border-gray-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-sky-300"
              />
            </div>
          </div>
        </div>

        {/* AI settings */}
        <div className="bg-white border border-gray-200 rounded-xl p-6">
          <h3 className="font-semibold text-gray-800 mb-4">Agente IA</h3>
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-gray-700">Procesar con IA</p>
                <p className="text-xs text-gray-400">Analizar cada propiedad con LLM</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" defaultChecked className="sr-only peer" />
                <div className="w-11 h-6 bg-gray-200 peer-focus:ring-2 peer-focus:ring-sky-300 rounded-full peer peer-checked:after:translate-x-full peer-checked:bg-[#2c3e50] after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all" />
              </label>
            </div>
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
    </div>
  )
}
