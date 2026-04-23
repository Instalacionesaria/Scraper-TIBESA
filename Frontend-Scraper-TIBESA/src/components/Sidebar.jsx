import { NavLink } from 'react-router-dom'
import { Building2, BarChart3, Settings, LogOut, Search, Facebook } from 'lucide-react'

const navItems = [
  { to: '/leads', label: 'Búsqueda de Leads', icon: Search },
  { to: '/facebook', label: 'Scrappers de Facebook', icon: Facebook },
  { to: '/', label: 'Scraper de Propiedades Específicas', icon: Building2 },
  { to: '/resultados', label: 'Resultados', icon: BarChart3 },
  { to: '/configuracion', label: 'Configuración', icon: Settings },
]

export default function Sidebar() {
  return (
    <aside className="w-56 bg-[#2c3e50] text-white flex flex-col min-h-screen fixed left-0 top-0">
      {/* Logo */}
      <div className="px-4 py-6 text-center border-b border-white/10">
        <div className="w-20 h-20 bg-white rounded-xl mx-auto mb-3 flex items-center justify-center p-2 shadow-md">
          <img
            src="/tibesa-logo.png"
            alt="TIBESA Bienes Raíces"
            className="w-full h-full object-contain"
          />
        </div>
        <h1 className="text-base font-bold tracking-wide">TIBESA</h1>
        <h2 className="text-xs font-medium text-white/80 -mt-0.5">Bienes Raíces</h2>
        <span className="text-[10px] tracking-[3px] text-white/50 uppercase">Scraper Suite</span>
      </div>

      {/* Navigation */}
      <nav className="flex-1 py-4">
        {navItems.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-5 py-3 text-sm transition-colors ${
                isActive
                  ? 'bg-white/15 border-l-3 border-white font-medium'
                  : 'text-white/70 hover:bg-white/5 hover:text-white border-l-3 border-transparent'
              }`
            }
          >
            <Icon className="w-4 h-4 shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-white/10">
        <div className="text-xs text-white/40 mb-2">
          Propiedades Scrapeadas
          <span className="float-right text-white font-semibold text-sm">0</span>
        </div>
        <div className="w-full bg-white/10 rounded-full h-1.5">
          <div className="bg-sky-400 h-1.5 rounded-full" style={{ width: '0%' }} />
        </div>
      </div>
    </aside>
  )
}
