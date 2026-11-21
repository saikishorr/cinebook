import { Component } from 'react'

// Catches a crash in any page so the visitor sees a way out instead of a blank screen.
export default class ErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { failed: false }
  }

  static getDerivedStateFromError() {
    return { failed: true }
  }

  componentDidCatch(error, info) {
    console.error('CineBook page error', error, info.componentStack)
  }

  render() {
    if (!this.state.failed) return this.props.children
    return (
      <main className="page-wrap">
        <div className="state-panel">
          <span className="state-icon">!</span>
          <h1>Something went wrong</h1>
          <p>This page hit an unexpected problem. Your seats and bookings are safe on our side.</p>
          <a className="button primary" href="/">Back to CineBook</a>
        </div>
      </main>
    )
  }
}
