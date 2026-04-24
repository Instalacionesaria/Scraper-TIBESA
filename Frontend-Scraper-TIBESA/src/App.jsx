import { Routes, Route, Navigate, useLocation } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import ScraperPage from './pages/ScraperPage'
import ResultadosPage from './pages/ResultadosPage'
import ConfiguracionPage from './pages/ConfiguracionPage'
import BusquedaLeadsPage from './pages/BusquedaLeadsPage'
import ScrappersFacebookPage from './pages/ScrappersFacebookPage'
import LoginPage from './pages/LoginPage'
import { hasCredentials } from './lib/auth'

function RequireAuth({ children }) {
  const location = useLocation()
  if (!hasCredentials()) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }
  return children
}

function Shell({ children }) {
  return (
    <div className="flex min-h-screen bg-gray-50">
      <Sidebar />
      <main className="flex-1 ml-56 p-8 min-w-0 overflow-hidden">{children}</main>
    </div>
  )
}

function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route
        path="/*"
        element={
          <RequireAuth>
            <Shell>
              <Routes>
                <Route path="/" element={<ScraperPage />} />
                <Route path="/leads" element={<BusquedaLeadsPage />} />
                <Route path="/facebook" element={<ScrappersFacebookPage />} />
                <Route path="/resultados" element={<ResultadosPage />} />
                <Route path="/configuracion" element={<ConfiguracionPage />} />
              </Routes>
            </Shell>
          </RequireAuth>
        }
      />
    </Routes>
  )
}

export default App
