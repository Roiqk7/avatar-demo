export type DevErrorDetails = {
  title: string
  message: string
  stack?: string
  meta?: Record<string, unknown>
}

export function DevErrorPopup(props: { error: DevErrorDetails | null; onClose: () => void }) {
  if (!props.error) return null

  const { title, message, stack, meta } = props.error
  const showMeta = meta && Object.keys(meta).length > 0

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="dev-error-popup"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.55)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 10000,
        padding: 16,
      }}
      onClick={props.onClose}
    >
      <div
        style={{
          width: 'min(920px, 100%)',
          maxHeight: '80vh',
          overflow: 'auto',
          borderRadius: 12,
          background: '#0b0b0c',
          border: '1px solid rgba(255,255,255,0.12)',
          padding: 16,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: 'rgba(255,255,255,0.9)' }}>{title}</div>
          <button
            type="button"
            onClick={props.onClose}
            style={{
              borderRadius: 10,
              padding: '6px 10px',
              border: '1px solid rgba(255,255,255,0.16)',
              background: 'rgba(255,255,255,0.06)',
              color: 'rgba(255,255,255,0.86)',
              cursor: 'pointer',
            }}
          >
            Close
          </button>
        </div>

        <div style={{ marginTop: 12 }}>
          <pre
            style={{
              margin: 0,
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
              fontSize: 12,
              lineHeight: 1.35,
              color: 'rgba(255,255,255,0.82)',
            }}
          >
            {message}
          </pre>
          {showMeta ? (
            <pre
              style={{
                marginTop: 12,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                fontSize: 12,
                lineHeight: 1.35,
                color: 'rgba(255,255,255,0.74)',
              }}
            >
              {JSON.stringify(meta, null, 2)}
            </pre>
          ) : null}
          {stack ? (
            <pre
              style={{
                marginTop: 12,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                fontSize: 11,
                lineHeight: 1.35,
                color: 'rgba(255,255,255,0.62)',
                opacity: 0.95,
              }}
            >
              {stack}
            </pre>
          ) : null}
        </div>
      </div>
    </div>
  )
}

