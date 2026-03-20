import { Power, Cpu, RefreshCw } from 'lucide-react'
import { useAgents, useGpu, useStackStatus, useStopStack, useRestartStack } from '../hooks/useBackend'
import { AgentCard } from '../components/AgentCard'

export function Dashboard() {
  const agents = useAgents()
  const gpu = useGpu()
  const stack = useStackStatus()
  const stopStack = useStopStack()
  const restart = useRestartStack()

  const runningCount = agents.data?.filter(a => a.running).length ?? 0
  const enabledCount = agents.data?.filter(a => a.enabled).length ?? 0

  return (
    <div className="space-y-6">
      {/* Stack control bar */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className={`w-2 h-2 rounded-full ${stack.data?.running ? 'bg-green-400' : 'bg-gray-600'}`} />
          <div>
            <p className="text-sm font-medium text-gray-200">
              {stack.data?.running ? 'Backend running' : 'Backend stopped'}
            </p>
            <p className="text-xs text-gray-500">
              {runningCount} of {enabledCount} agents active
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => restart.mutate()}
            disabled={restart.isPending}
            title="Restart backend"
            className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 text-gray-400 transition-colors"
          >
            <RefreshCw className={`w-4 h-4 ${restart.isPending ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => stopStack.mutate()}
            disabled={stopStack.isPending || !stack.data?.running}
            className="flex items-center gap-2 bg-red-900/50 hover:bg-red-800/50 disabled:opacity-30 text-red-400 text-sm font-medium px-3 py-2 rounded-lg transition-colors"
          >
            <Power className="w-4 h-4" />
            Stop
          </button>
        </div>
      </div>

      {/* GPU info */}
      {gpu.data && (
        <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-3">
            <Cpu className="w-4 h-4 text-brand-400" />
            <span className="text-sm font-medium text-gray-300">{gpu.data.name}</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex-1 bg-gray-800 rounded-full h-2">
              <div
                className="bg-brand-500 h-2 rounded-full transition-all"
                style={{ width: `${(gpu.data.vram_used_gb / gpu.data.vram_total_gb) * 100}%` }}
              />
            </div>
            <span className="text-xs text-gray-400 flex-shrink-0">
              {gpu.data.vram_used_gb} / {gpu.data.vram_total_gb} GB VRAM
            </span>
          </div>
        </div>
      )}

      {/* Agent cards */}
      <div className="space-y-3">
        <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Agents</h2>
        {agents.isLoading ? (
          <div className="text-center py-8 text-gray-600">Loading agents…</div>
        ) : agents.data?.length === 0 ? (
          <div className="text-center py-8 text-gray-600">No agents configured yet. Go to Setup.</div>
        ) : (
          agents.data?.map(agent => (
            <AgentCard key={agent.slot} agent={agent} />
          ))
        )}
      </div>
    </div>
  )
}
