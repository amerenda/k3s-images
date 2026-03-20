import { AlertTriangle, CheckCircle } from 'lucide-react'
import { useVramCheck } from '../hooks/useBackend'

interface Props {
  models: string[]
}

export function VramWarning({ models }: Props) {
  const { data, isLoading } = useVramCheck(models)

  if (!data || isLoading || models.length === 0) return null

  return (
    <div className={`rounded-xl p-4 border ${
      data.fits_simultaneously
        ? 'bg-green-950/30 border-green-800'
        : 'bg-amber-950/30 border-amber-700'
    }`}>
      <div className="flex items-start gap-3">
        {data.fits_simultaneously ? (
          <CheckCircle className="w-5 h-5 text-green-400 flex-shrink-0 mt-0.5" />
        ) : (
          <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
        )}
        <div className="flex-1 min-w-0">
          <p className={`text-sm font-medium ${data.fits_simultaneously ? 'text-green-300' : 'text-amber-300'}`}>
            {data.fits_simultaneously
              ? 'Models fit in GPU memory'
              : 'Models exceed GPU memory'}
          </p>
          <p className="text-xs text-gray-400 mt-1">
            Total needed: <span className="text-gray-200">{data.total_vram_needed_gb} GB</span>
            {' / '}
            GPU available: <span className="text-gray-200">{data.gpu_vram_gb} GB</span>
          </p>

          <div className="mt-2 space-y-1">
            {data.per_model.map(m => (
              <div key={m.model} className="flex items-center justify-between text-xs">
                <span className="text-gray-400 truncate">{m.model}</span>
                <span className="text-gray-300 ml-2 flex-shrink-0">{m.vram_gb} GB</span>
              </div>
            ))}
          </div>

          {data.warning && (
            <p className="text-xs text-amber-400 mt-2">{data.warning}</p>
          )}

          {!data.fits_simultaneously && (
            <p className="text-xs text-gray-400 mt-2">
              Agents will be automatically scheduled at staggered times so they don't run models simultaneously.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
