import { Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import ScraperPage from './pages/ScraperPage'
import ResultadosPage from './pages/ResultadosPage'
import ConfiguracionPage from './pages/ConfiguracionPage'
import BusquedaLeadsPage from './pages/BusquedaLeadsPage'
import ScrappersFacebookPage from './pages/ScrappersFacebookPage'

function App() {
  return (
    <div className="flex min-h-screen bg-gray-50">
      <Sidebar />
      <main className="flex-1 ml-56 p-8">
        <Routes>
          <Route path="/" element={<ScraperPage />} />
          <Route path="/leads" element={<BusquedaLeadsPage />} />
          <Route path="/facebook" element={<ScrappersFacebookPage />} />
          <Route path="/resultados" element={<ResultadosPage />} />
          <Route path="/configuracion" element={<ConfiguracionPage />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
