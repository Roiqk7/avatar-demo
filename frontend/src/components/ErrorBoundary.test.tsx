import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ErrorBoundary } from './ErrorBoundary'

function Bomb({ shouldThrow }: { shouldThrow: boolean }) {
  if (shouldThrow) throw new Error('Test explosion')
  return <div>Safe content</div>
}

describe('ErrorBoundary', () => {
  beforeEach(() => {
    // Suppress React's error boundary console noise during tests
    vi.spyOn(console, 'error').mockImplementation(() => {})
  })

  it('renders children when there is no error', () => {
    render(
      <ErrorBoundary>
        <div>Hello world</div>
      </ErrorBoundary>,
    )
    expect(screen.getByText('Hello world')).toBeInTheDocument()
  })

  it('renders fallback UI when a child throws', () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow />
      </ErrorBoundary>,
    )
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument()
  })

  it('fallback contains a Reload button', () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow />
      </ErrorBoundary>,
    )
    expect(screen.getByRole('button', { name: /reload/i })).toBeInTheDocument()
  })

  it('does not render children after an error', () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow />
      </ErrorBoundary>,
    )
    expect(screen.queryByText('Safe content')).not.toBeInTheDocument()
  })

  it('calls console.error when catching an error', () => {
    render(
      <ErrorBoundary>
        <Bomb shouldThrow />
      </ErrorBoundary>,
    )
    expect(console.error).toHaveBeenCalled()
  })

  it('Reload button calls window.location.reload', async () => {
    const reload = vi.fn()
    Object.defineProperty(window, 'location', {
      value: { reload },
      writable: true,
    })

    render(
      <ErrorBoundary>
        <Bomb shouldThrow />
      </ErrorBoundary>,
    )

    await userEvent.click(screen.getByRole('button', { name: /reload/i }))
    expect(reload).toHaveBeenCalledOnce()
  })
})
