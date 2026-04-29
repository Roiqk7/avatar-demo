import type { Personality } from '../types'

export function PersonalityPicker(props: {
  personalities: Personality[]
  activeId: string | null
  onSelect: (id: string) => void
  disabled?: boolean
}) {
  const { personalities, activeId, onSelect, disabled } = props
  return (
    <div className="personality-grid" id="personality-grid">
      {personalities.map((p) => {
        const active = activeId === p.id
        return (
          <button
            key={p.id}
            type="button"
            className={'p-btn' + (active ? ' active' : '')}
            onClick={() => onSelect(p.id)}
            disabled={disabled}
          >
            <div className="p-name">{p.display_name}</div>
          </button>
        )
      })}
    </div>
  )
}

