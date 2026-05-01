import * as React from 'react'

type Props = { children: React.ReactNode }
type State = { error: Error | null }

export class ErrorBoundary extends React.Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: React.ErrorInfo): void {
    console.error('[ErrorBoundary] Uncaught error:', error, info)
  }

  render(): React.ReactNode {
    if (this.state.error) {
      return (
        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            height: '100dvh',
            gap: '1rem',
            fontFamily: 'system-ui, sans-serif',
            color: '#1a1d2e',
            background: '#f4f6fb',
            padding: '2rem',
            textAlign: 'center',
          }}
        >
          <h2 style={{ margin: 0 }}>Something went wrong</h2>
          <p style={{ margin: 0, color: '#6b7897', maxWidth: 400 }}>
            An unexpected error occurred. Reloading the page usually fixes it.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '0.6rem 1.4rem',
              borderRadius: 8,
              border: 'none',
              background: '#3b4fe4',
              color: '#fff',
              fontSize: '0.95rem',
              cursor: 'pointer',
            }}
          >
            Reload
          </button>
        </div>
      )
    }
    return this.props.children
  }
}
