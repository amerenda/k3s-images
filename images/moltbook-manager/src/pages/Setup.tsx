import { useState, useEffect } from 'react'
import { Save, Plus, Minus } from 'lucide-react'
import { useAgents, useModels, useUpdateAgent } from '../hooks/useBackend'
import { VramWarning } from '../components/VramWarning'
import type { Agent } from '../types'

function AgentSetupPanel({ agent, models }: { agent: Agent; models: { name: string; vram_estimate_gb: number }[] }) {
  const update = useUpdateAgent()
  const [form, setForm] = useState({
    model: agent.model,
    name: agent.persona.name,
    description: agent.persona.description,
    tone: agent.persona.tone,
    topics: agent.persona.topics.join(', '),
    post_interval_minutes: agent.schedule.post_interval_minutes,
    active_hours_start: agent.schedule.active_hours_start,
    active_hours_end: agent.schedule.active_hours_end,
    max_post_length: agent.behavior.max_post_length,
    auto_reply: agent.behavior.auto_reply,
    auto_like: agent.behavior.auto_like,
  })
  const [saved, setSaved] = useState(false)

  async function handleSave() {
    await update.mutateAsync({
      slot: agent.slot,
      data: {
        model: form.model,
        persona: {
          name: form.name,
          description: form.description,
          tone: form.tone,
          topics: form.topics.split(',').map(t => t.trim()).filter(Boolean),
        },
        schedule: {
          post_interval_minutes: form.post_interval_minutes,
          active_hours_start: form.active_hours_start,
          active_hours_end: form.active_hours_end,
        },
        behavior: {
          max_post_length: form.max_post_length,
          auto_reply: form.auto_reply,
          auto_like: form.auto_like,
        },
      },
    })
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-5 space-y-4">
      <h3 className="font-medium text-gray-200">Agent {agent.slot}</h3>

      {/* Model */}
      <div>
        <label className="block text-xs text-gray-500 mb-1">Model</label>
        <select
          value={form.model}
          onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
        >
          {models.map(m => (
            <option key={m.name} value={m.name}>
              {m.name} ({m.vram_estimate_gb} GB VRAM)
            </option>
          ))}
        </select>
      </div>

      {/* Name */}
      <div>
        <label className="block text-xs text-gray-500 mb-1">Moltbook username</label>
        <input
          value={form.name}
          onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
        />
      </div>

      {/* Bio */}
      <div>
        <label className="block text-xs text-gray-500 mb-1">Bio</label>
        <textarea
          value={form.description}
          onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
          rows={2}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500 resize-none"
        />
      </div>

      {/* Tone */}
      <div>
        <label className="block text-xs text-gray-500 mb-1">Tone / personality</label>
        <input
          value={form.tone}
          onChange={e => setForm(f => ({ ...f, tone: e.target.value }))}
          placeholder="e.g. curious, witty, occasionally sarcastic"
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
        />
      </div>

      {/* Topics */}
      <div>
        <label className="block text-xs text-gray-500 mb-1">Topics (comma separated)</label>
        <input
          value={form.topics}
          onChange={e => setForm(f => ({ ...f, topics: e.target.value }))}
          placeholder="e.g. technology, coffee, music"
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
        />
      </div>

      {/* Schedule */}
      <div className="grid grid-cols-3 gap-3">
        <div>
          <label className="block text-xs text-gray-500 mb-1">Post every (min)</label>
          <input
            type="number"
            min={30}
            value={form.post_interval_minutes}
            onChange={e => setForm(f => ({ ...f, post_interval_minutes: +e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Active from (h)</label>
          <input
            type="number"
            min={0} max={23}
            value={form.active_hours_start}
            onChange={e => setForm(f => ({ ...f, active_hours_start: +e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
          />
        </div>
        <div>
          <label className="block text-xs text-gray-500 mb-1">Active until (h)</label>
          <input
            type="number"
            min={1} max={24}
            value={form.active_hours_end}
            onChange={e => setForm(f => ({ ...f, active_hours_end: +e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
          />
        </div>
      </div>

      {/* Behavior toggles */}
      <div className="flex gap-4">
        <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
          <input
            type="checkbox"
            checked={form.auto_reply}
            onChange={e => setForm(f => ({ ...f, auto_reply: e.target.checked }))}
            className="accent-brand-500"
          />
          Auto-reply
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
          <input
            type="checkbox"
            checked={form.auto_like}
            onChange={e => setForm(f => ({ ...f, auto_like: e.target.checked }))}
            className="accent-brand-500"
          />
          Auto-like
        </label>
      </div>

      <button
        onClick={handleSave}
        disabled={update.isPending}
        className="flex items-center gap-2 bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
      >
        <Save className="w-4 h-4" />
        {saved ? 'Saved!' : update.isPending ? 'Saving…' : 'Save'}
      </button>
    </div>
  )
}

export function Setup() {
  const agents = useAgents()
  const models = useModels()
  const update = useUpdateAgent()

  const [agentCount, setAgentCount] = useState(1)

  useEffect(() => {
    if (agents.data) {
      setAgentCount(Math.max(1, agents.data.filter(a => a.enabled || a.registered).length) || 1)
    }
  }, [agents.data])

  const selectedModels = agents.data
    ?.slice(0, agentCount)
    .map(a => a.model) ?? []

  async function handleCountChange(count: number) {
    setAgentCount(count)
    // Disable agents beyond the new count
    if (agents.data) {
      for (const agent of agents.data) {
        if (agent.slot > count && agent.enabled) {
          await update.mutateAsync({ slot: agent.slot, data: { enabled: false } })
        }
      }
    }
  }

  return (
    <div className="space-y-6">
      {/* Agent count selector */}
      <div className="bg-gray-900 border border-gray-800 rounded-xl p-5">
        <h2 className="text-sm font-medium text-gray-300 mb-4">How many agents?</h2>
        <div className="flex items-center gap-4">
          <button
            onClick={() => agentCount > 1 && handleCountChange(agentCount - 1)}
            disabled={agentCount <= 1}
            className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-30 text-gray-300 transition-colors"
          >
            <Minus className="w-4 h-4" />
          </button>
          <div className="flex gap-2">
            {[1, 2, 3, 4, 5, 6].map(n => (
              <button
                key={n}
                onClick={() => handleCountChange(n)}
                className={`w-10 h-10 rounded-xl font-bold text-sm transition-colors ${
                  agentCount === n
                    ? 'bg-brand-600 text-white'
                    : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                }`}
              >
                {n}
              </button>
            ))}
          </div>
          <button
            onClick={() => agentCount < 6 && handleCountChange(agentCount + 1)}
            disabled={agentCount >= 6}
            className="p-2 rounded-lg bg-gray-800 hover:bg-gray-700 disabled:opacity-30 text-gray-300 transition-colors"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* VRAM warning */}
      {selectedModels.length > 0 && (
        <VramWarning models={selectedModels} />
      )}

      {/* Per-agent config panels */}
      {agents.isLoading ? (
        <div className="text-center py-8 text-gray-600">Loading…</div>
      ) : (
        agents.data?.slice(0, agentCount).map(agent => (
          <AgentSetupPanel
            key={agent.slot}
            agent={agent}
            models={models.data ?? []}
          />
        ))
      )}
    </div>
  )
}
