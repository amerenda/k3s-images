import { Routes, Route, NavLink, useLocation } from 'react-router-dom'
import { LayoutDashboard, Settings, UserPlus, Loader2, WifiOff } from 'lucide-react'
import { useHealth } from './hooks/useBackend'
import { BackendOffline } from './components/BackendOffline'
import { Dashboard } from './pages/Dashboard'
import { Setup } from './pages/Setup'
import { Register } from './pages/Register'

const navItems = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/setup', label: 'Setup', icon: Settings },
  { to: '/register', label: 'Register', icon: UserPlus },
]

function NavBar() {
  return (
    <nav className="bg-gray-900 border-b border-gray-800">
      <div className="max-w-3xl mx-auto px-4 flex items-center justify-between h-14">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-brand-600 flex items-center justify-center">
            <span className="text-white text-xs font-bold">M</span>
          </div>
          <span className="font-semibold text-gray-100 text-sm">Moltbook Manager</span>
        </div>
        <div className="flex gap-1">
          {navItems.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                `flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-brand-900 text-brand-300'
                    : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
                }`
              }
            >
              <Icon className="w-4 h-4" />
              <span className="hidden sm:inline">{label}</span>
            </NavLink>
          ))}
        </div>
      </div>
    </nav>
  )
}

export default function App() {
  const health = useHealth()

  // Still loading first check
  if (health.isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-6 h-6 text-gray-600 animate-spin" />
      </div>
    )
  }

  // Controller itself is unreachable (pod down or network issue)
  if (health.isError && (health.error as Error).message.includes('fetch')) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <WifiOff className="w-8 h-8 text-gray-600 mx-auto mb-3" />
          <p className="text-gray-400 text-sm">Cannot reach controller</p>
        </div>
      </div>
    )
  }

  // Backend is down (503 from controller)
  if (health.isError) {
    return <BackendOffline />
  }

  return (
    <div className="min-h-screen">
      <NavBar />
      <main className="max-w-3xl mx-auto px-4 py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/setup" element={<Setup />} />
          <Route path="/register" element={<Register />} />
        </Routes>
      </main>
    </div>
  )
}
