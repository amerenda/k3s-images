import { AlertTriangle, Power } from 'lucide-react'
import { useStartStack, useStackStatus } from '../hooks/useBackend'

export function BackendOffline() {
  const start = useStartStack()
  const stack = useStackStatus()

  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="max-w-md w-full mx-4">
        <div className="bg-gray-900 border border-gray-800 rounded-2xl p-8 text-center">
          <div className="flex justify-center mb-4">
            <div className="w-16 h-16 rounded-full bg-red-950 flex items-center justify-center">
              <AlertTriangle className="w-8 h-8 text-red-400" />
            </div>
          </div>
          <h1 className="text-xl font-semibold text-gray-100 mb-2">Backend Offline</h1>
          <p className="text-gray-400 text-sm mb-6">
            The Moltbook backend isn't running on murderbot. Start it to manage your agents.
          </p>

          {stack.data && (
            <div className="mb-6 text-left bg-gray-950 rounded-lg p-3">
              <p className="text-xs text-gray-500 mb-2">Docker stack status</p>
              {stack.data.services.length === 0 ? (
                <p className="text-xs text-gray-600">No containers found</p>
              ) : (
                stack.data.services.map(s => (
                  <div key={s.id} className="flex items-center justify-between text-xs py-1">
                    <span className="text-gray-400">{s.name}</span>
                    <span className={s.status === 'running' ? 'text-green-400' : 'text-red-400'}>
                      {s.status}
                    </span>
                  </div>
                ))
              )}
            </div>
          )}

          <button
            onClick={() => start.mutate()}
            disabled={start.isPending}
            className="w-full flex items-center justify-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white font-medium py-3 px-6 rounded-xl transition-colors"
          >
            <Power className="w-4 h-4" />
            {start.isPending ? 'Starting…' : 'Start Backend'}
          </button>

          {start.isError && (
            <p className="mt-3 text-xs text-red-400">
              Failed: {(start.error as Error).message}
            </p>
          )}
          {start.isSuccess && (
            <p className="mt-3 text-xs text-green-400">
              Started — reloading…
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
