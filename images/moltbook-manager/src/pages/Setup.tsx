import { useState } from 'react'
import { Save, Plus, Trash2, Power, Info, AlertTriangle, HelpCircle } from 'lucide-react'
import { useAgents, useModels, useUpdateAgent, useDeleteAgent, useGpu } from '../hooks/useBackend'
import type { Agent } from '../types'

// ── Tooltip ───────────────────────────────────────────────────────────────────

function Tip({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  return (
    <span className="relative inline-flex">
      <button
        type="button"
        className="text-gray-600 hover:text-gray-400 transition-colors ml-1"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onClick={e => { e.preventDefault(); setOpen(o => !o) }}
        aria-label="Help"
      >
        <HelpCircle className="w-3.5 h-3.5" />
      </button>
      {open && (
        <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 z-50 w-60 bg-gray-800 border border-gray-700 rounded-lg p-2.5 text-xs text-gray-300 shadow-xl pointer-events-none block">
          <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-700" />
          {text}
        </span>
      )}
    </span>
  )
}

// ── VRAM overlap helper ───────────────────────────────────────────────────────

function maxConcurrentVram(agents: Agent[], modelVram: Record<string, number>): number {
  const active = agents.filter(a => a.enabled)
  if (active.length === 0) return 0
  let max = 0
  for (let h = 0; h < 24; h++) {
    const concurrent = active.filter(a => {
      const { active_hours_start: s, active_hours_end: e } = a.schedule
      return s <= e ? h >= s && h < e : h >= s || h < e
    })
    const vram = concurrent.reduce((sum, a) => sum + (modelVram[a.model] ?? 4.5), 0)
    if (vram > max) max = vram
  }
  return max
}

// ── Delete confirmation ───────────────────────────────────────────────────────

function DeleteConfirm({ agent, onConfirm, onCancel }: {
  agent: Agent
  onConfirm: () => void
  onCancel: () => void
}) {
  return (
    <div className="rounded-xl border border-red-800 bg-red-950/30 p-4 space-y-3">
      {agent.registered && (
        <div className="flex gap-2 text-sm text-amber-300">
          <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
          <span>
            <strong>{agent.persona.name}</strong> is registered on Moltbook. Deleting removes the
            local config only — the Moltbook account will still exist.
          </span>
        </div>
      )}
      <p className="text-sm text-gray-300">
        Delete <strong>{agent.persona.name}</strong>? This cannot be undone.
      </p>
      <div className="flex gap-2">
        <button
          onClick={onConfirm}
          className="bg-red-700 hover:bg-red-600 text-white text-sm font-medium px-3 py-1.5 rounded-lg transition-colors"
        >
          Delete
        </button>
        <button
          onClick={onCancel}
          className="bg-gray-800 hover:bg-gray-700 text-gray-300 text-sm px-3 py-1.5 rounded-lg transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

// ── Agent config panel ────────────────────────────────────────────────────────

function AgentSetupPanel({
  agent,
  models,
  onDelete,
}: {
  agent: Agent
  models: { name: string; vram_estimate_gb: number }[]
  onDelete: () => void
}) {
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
    reply_to_own_threads: agent.behavior.reply_to_own_threads,
    post_jitter_pct: agent.behavior.post_jitter_pct,
    karma_throttle: agent.behavior.karma_throttle,
    karma_throttle_threshold: agent.behavior.karma_throttle_threshold,
    karma_throttle_multiplier: agent.behavior.karma_throttle_multiplier,
    target_submolts: agent.behavior.target_submolts.join(', '),
    auto_dm_approve: agent.behavior.auto_dm_approve,
  })
  const [saved, setSaved] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

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
          reply_to_own_threads: form.reply_to_own_threads,
          post_jitter_pct: form.post_jitter_pct,
          karma_throttle: form.karma_throttle,
          karma_throttle_threshold: form.karma_throttle_threshold,
          karma_throttle_multiplier: form.karma_throttle_multiplier,
          target_submolts: form.target_submolts.split(',').map((s: string) => s.trim()).filter(Boolean),
          auto_dm_approve: form.auto_dm_approve,
        },
      },
    })
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  async function handleToggleActive() {
    await update.mutateAsync({ slot: agent.slot, data: { enabled: !agent.enabled } })
  }

  return (
    <div className="space-y-4">

      {/* Active toggle + delete */}
      <div className="flex items-center justify-between">
        <button
          onClick={handleToggleActive}
          disabled={update.isPending}
          className={`flex items-center gap-2 text-sm font-medium px-3 py-1.5 rounded-lg transition-colors ${
            agent.enabled
              ? 'bg-green-900/50 text-green-300 hover:bg-green-800/50'
              : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
          }`}
        >
          <Power className="w-4 h-4" />
          {agent.enabled ? 'Active' : 'Inactive'}
        </button>
        <button
          onClick={() => setConfirmDelete(true)}
          className="flex items-center gap-1.5 text-sm text-gray-500 hover:text-red-400 transition-colors px-2 py-1.5"
        >
          <Trash2 className="w-4 h-4" />
          Delete
        </button>
      </div>

      {confirmDelete && (
        <DeleteConfirm
          agent={agent}
          onConfirm={onDelete}
          onCancel={() => setConfirmDelete(false)}
        />
      )}

      {/* Model */}
      <div>
        <label className="flex items-center text-xs text-gray-500 mb-1">
          Model
          <Tip text="Which Ollama model drives this agent. Larger models write better but need more VRAM and are slower to respond." />
        </label>
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
        <label className="flex items-center text-xs text-gray-500 mb-1">
          Moltbook username
          <Tip text="The agent's display name on Moltbook. Pick carefully — it cannot be changed after registration." />
        </label>
        <input
          value={form.name}
          onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
        />
      </div>

      {/* Bio */}
      <div>
        <label className="flex items-center text-xs text-gray-500 mb-1">
          Bio
          <Tip text="Short description shown on the agent's Moltbook profile page." />
        </label>
        <textarea
          value={form.description}
          onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
          rows={2}
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500 resize-none"
        />
      </div>

      {/* Tone */}
      <div>
        <label className="flex items-center text-xs text-gray-500 mb-1">
          Tone / personality
          <Tip text="Freeform style instruction fed directly to the LLM system prompt. Shapes how the agent writes — e.g. 'dry wit, concise, slightly cynical'." />
        </label>
        <input
          value={form.tone}
          onChange={e => setForm(f => ({ ...f, tone: e.target.value }))}
          placeholder="e.g. curious, witty, occasionally sarcastic"
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
        />
      </div>

      {/* Topics */}
      <div>
        <label className="flex items-center text-xs text-gray-500 mb-1">
          Topics
          <Tip text="Subjects the agent posts about. Also used as the default submolt when no target submolts are set." />
        </label>
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
          <label className="flex items-center text-xs text-gray-500 mb-1">
            Post every (min)
            <Tip text="Minimum time between autonomous posts. Actual timing also varies by the jitter setting below." />
          </label>
          <input
            type="number" min={30}
            value={form.post_interval_minutes}
            onChange={e => setForm(f => ({ ...f, post_interval_minutes: +e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
          />
        </div>
        <div>
          <label className="flex items-center text-xs text-gray-500 mb-1">
            Active from (h)
            <Tip text="Hour the agent starts being allowed to post (24h clock, local time)." />
          </label>
          <input
            type="number" min={0} max={23}
            value={form.active_hours_start}
            onChange={e => setForm(f => ({ ...f, active_hours_start: +e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
          />
        </div>
        <div>
          <label className="flex items-center text-xs text-gray-500 mb-1">
            Active until (h)
            <Tip text="Hour the agent stops posting (24h clock, local time). Set end earlier than start for overnight windows." />
          </label>
          <input
            type="number" min={1} max={24}
            value={form.active_hours_end}
            onChange={e => setForm(f => ({ ...f, active_hours_end: +e.target.value }))}
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
          />
        </div>
      </div>

      {/* Behavior toggles row 1 */}
      <div className="flex gap-4 flex-wrap">
        <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
          <input type="checkbox" checked={form.auto_reply}
            onChange={e => setForm(f => ({ ...f, auto_reply: e.target.checked }))}
            className="accent-brand-500" />
          Auto-reply
          <Tip text="Replies to comments other users leave on this agent's posts. Each heartbeat processes up to 5 new comments." />
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
          <input type="checkbox" checked={form.auto_like}
            onChange={e => setForm(f => ({ ...f, auto_like: e.target.checked }))}
            className="accent-brand-500" />
          Auto-like
          <Tip text="Upvotes posts encountered while browsing the feed. Helps build karma and presence without posting." />
        </label>
      </div>

      {/* Post jitter */}
      <div>
        <label className="flex items-center text-xs text-gray-500 mb-1">
          Post timing jitter ({form.post_jitter_pct}%)
          <Tip text="Adds a random offset to the post interval each cycle. At 20%, a 60-min interval becomes anywhere from 48–72 min. Prevents agents from posting on a robotic fixed clock." />
        </label>
        <input
          type="range" min={0} max={50} step={5}
          value={form.post_jitter_pct}
          onChange={e => setForm(f => ({ ...f, post_jitter_pct: +e.target.value }))}
          className="w-full accent-brand-500"
        />
        <p className="text-xs text-gray-600 mt-0.5">
          Randomizes post interval ±{form.post_jitter_pct}%
        </p>
      </div>

      {/* Target submolts */}
      <div>
        <label className="flex items-center text-xs text-gray-500 mb-1">
          Target submolts
          <Tip text="Pin posts to specific communities (e.g. 'technology, science'). If blank, the agent derives a submolt from its topics list. One is chosen at random each post." />
        </label>
        <input
          value={form.target_submolts}
          onChange={e => setForm(f => ({ ...f, target_submolts: e.target.value }))}
          placeholder="e.g. technology, science (leave blank to use topics)"
          className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
        />
      </div>

      {/* Behavior toggles row 2 */}
      <div className="flex flex-wrap gap-4">
        <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
          <input type="checkbox" checked={form.reply_to_own_threads}
            onChange={e => setForm(f => ({ ...f, reply_to_own_threads: e.target.checked }))}
            className="accent-brand-500" />
          Extend threads
          <Tip text="After heartbeat, occasionally adds a follow-up comment to this agent's own recent posts — continuing the thread with a new thought. Other agents (and humans) on the platform may then reply to that continuation." />
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
          <input type="checkbox" checked={form.auto_dm_approve}
            onChange={e => setForm(f => ({ ...f, auto_dm_approve: e.target.checked }))}
            className="accent-brand-500" />
          Auto-approve DMs
          <Tip text="Automatically accepts incoming DM requests without manual approval. Turn off if you want to vet who can DM this agent." />
        </label>
        <label className="flex items-center gap-2 text-sm text-gray-400 cursor-pointer">
          <input type="checkbox" checked={form.karma_throttle}
            onChange={e => setForm(f => ({ ...f, karma_throttle: e.target.checked }))}
            className="accent-brand-500" />
          Karma throttle
          <Tip text="Automatically slows down posting when the agent's karma drops below a threshold. Useful for laying low after a bad run without disabling the agent entirely." />
        </label>
      </div>

      {/* Karma throttle detail */}
      {form.karma_throttle && (
        <div className="grid grid-cols-2 gap-3 pl-4 border-l-2 border-gray-700">
          <div>
            <label className="flex items-center text-xs text-gray-500 mb-1">
              Throttle below karma
              <Tip text="If the agent's karma is below this number, the post interval is multiplied. The agent still posts — just less often." />
            </label>
            <input
              type="number" min={0}
              value={form.karma_throttle_threshold}
              onChange={e => setForm(f => ({ ...f, karma_throttle_threshold: +e.target.value }))}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
            />
          </div>
          <div>
            <label className="flex items-center text-xs text-gray-500 mb-1">
              Interval multiplier
              <Tip text="How much to stretch the post interval when karma is low. 2× means half as often, 3× means one-third as often." />
            </label>
            <input
              type="number" min={1} max={10} step={0.5}
              value={form.karma_throttle_multiplier}
              onChange={e => setForm(f => ({ ...f, karma_throttle_multiplier: +e.target.value }))}
              className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-2 text-gray-100 text-sm focus:outline-none focus:border-brand-500"
            />
          </div>
        </div>
      )}

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

// ── Schedule VRAM warning ─────────────────────────────────────────────────────

function ScheduleVramWarning({ agents, models }: {
  agents: Agent[]
  models: { name: string; vram_estimate_gb: number }[]
}) {
  const gpu = useGpu()
  const gpuVram = gpu.data?.vram_total_gb ?? 0
  if (gpuVram === 0) return null

  const modelVram: Record<string, number> = {}
  for (const m of models) modelVram[m.name] = m.vram_estimate_gb

  const peak = maxConcurrentVram(agents, modelVram)
  if (peak === 0) return null

  const fits = peak <= gpuVram

  return (
    <div className={`flex items-start gap-2 rounded-lg px-3 py-2 text-xs ${
      fits
        ? 'bg-gray-800/50 text-gray-500'
        : 'bg-amber-950/40 border border-amber-800/50 text-amber-300'
    }`}>
      {fits
        ? <Info className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />
        : <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-shrink-0" />}
      <span>
        Peak concurrent VRAM: <strong>{peak.toFixed(1)} GB</strong> / {gpuVram} GB
        {!fits && ' — overlapping active windows exceed GPU memory. Stagger schedules or use smaller models.'}
      </span>
    </div>
  )
}

// ── Main Setup page ───────────────────────────────────────────────────────────

function tabLabel(agent: Agent): string {
  return agent.persona.name !== 'Agent' ? agent.persona.name : `Agent ${agent.slot}`
}

function isCreated(a: Agent) {
  return a.enabled || a.registered || a.persona.name !== 'Agent'
}

export function Setup() {
  const agents = useAgents()
  const models = useModels()
  const update = useUpdateAgent()
  const deleteAgent = useDeleteAgent()

  const [activeTab, setActiveTab] = useState<number | null>(null)

  const allAgents = agents.data ?? []
  const created = allAgents.filter(isCreated)
  const canCreate = allAgents.some(a => !isCreated(a))

  const displayTab = activeTab !== null && created.some(a => a.slot === activeTab)
    ? activeTab
    : created[0]?.slot ?? null

  async function handleCreate() {
    const next = allAgents.find(a => !isCreated(a))
    if (!next) return
    await update.mutateAsync({ slot: next.slot, data: { enabled: true } })
    setActiveTab(next.slot)
  }

  async function handleDelete(slot: number) {
    await deleteAgent.mutateAsync(slot)
    if (displayTab === slot) {
      const remaining = created.filter(a => a.slot !== slot)
      setActiveTab(remaining[0]?.slot ?? null)
    }
  }

  if (agents.isLoading) {
    return <div className="text-center py-12 text-gray-600">Loading…</div>
  }

  return (
    <div className="space-y-4">

      {/* VRAM warning */}
      {created.length > 0 && models.data && (
        <ScheduleVramWarning agents={created} models={models.data} />
      )}

      {/* Tab strip */}
      <div className="flex items-center gap-1 border-b border-gray-800">
        {created.map(agent => (
          <button
            key={agent.slot}
            onClick={() => setActiveTab(agent.slot)}
            className={`relative px-4 py-2 text-sm font-medium rounded-t-lg transition-colors -mb-px ${
              displayTab === agent.slot
                ? 'bg-gray-900 border border-b-gray-900 border-gray-800 text-gray-100'
                : 'text-gray-500 hover:text-gray-300'
            }`}
          >
            <span className="flex items-center gap-1.5">
              <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${agent.enabled ? 'bg-green-400' : 'bg-gray-600'}`} />
              {tabLabel(agent)}
            </span>
          </button>
        ))}

        {canCreate && (
          <button
            onClick={handleCreate}
            disabled={update.isPending}
            className="flex items-center gap-1 px-3 py-2 text-sm text-gray-500 hover:text-brand-400 transition-colors ml-1"
          >
            <Plus className="w-4 h-4" />
            Create Agent
          </button>
        )}
      </div>

      {/* Tab content */}
      {displayTab !== null ? (
        (() => {
          const agent = created.find(a => a.slot === displayTab)
          if (!agent) return null
          return (
            <div className="bg-gray-900 border border-gray-800 rounded-b-xl rounded-tr-xl p-5">
              <AgentSetupPanel
                key={agent.slot}
                agent={agent}
                models={models.data ?? []}
                onDelete={() => handleDelete(agent.slot)}
              />
            </div>
          )
        })()
      ) : (
        <div className="text-center py-16 text-gray-600">
          <p className="mb-4">No agents yet.</p>
          <button
            onClick={handleCreate}
            disabled={!canCreate || update.isPending}
            className="flex items-center gap-2 mx-auto bg-brand-600 hover:bg-brand-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            <Plus className="w-4 h-4" />
            Create Agent
          </button>
        </div>
      )}
    </div>
  )
}
