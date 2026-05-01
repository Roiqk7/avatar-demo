import '@testing-library/jest-dom'

// JSDOM doesn't ship ResizeObserver; components like WaveformVisualizer rely on it.
class TestResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// @ts-ignore - test environment shim
globalThis.ResizeObserver = globalThis.ResizeObserver ?? TestResizeObserver
