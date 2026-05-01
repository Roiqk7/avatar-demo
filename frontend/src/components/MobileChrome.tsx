type Props = {
  isOptionsOpen: boolean
  onOpen: () => void
  onClose: () => void
  optionsContent: React.ReactNode
}

export function MobileChrome({ isOptionsOpen, onOpen, onClose, optionsContent }: Props) {
  return (
    <>
      <div className="mobile-chrome" aria-hidden={isOptionsOpen ? 'true' : undefined}>
        <a className="logo-link" href="https://ai-avatar.signosoft.com">
          <img src="/logo_full.png" alt="Signosoft" className="mobile-corner-logo" />
        </a>
        <button type="button" className="mobile-options-fab" onClick={onOpen} aria-label="Open options">
          Options
        </button>
      </div>

      {isOptionsOpen ? (
        <div className="mobile-sheet-backdrop" role="presentation" onClick={onClose}>
          <div className="mobile-sheet" role="dialog" aria-label="Options" onClick={(e) => e.stopPropagation()}>
            <div className="mobile-sheet-header">
              <div className="mobile-sheet-title">Options</div>
              <button type="button" className="mobile-sheet-close" onClick={onClose} aria-label="Close options">
                ✕
              </button>
            </div>
            {optionsContent}
          </div>
        </div>
      ) : null}
    </>
  )
}
