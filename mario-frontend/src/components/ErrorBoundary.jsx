import React from 'react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    // Update state so the next render shows the fallback UI.
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    // You could also log the error to an error reporting service here later
    console.error("🛡️ ErrorBoundary caught a crash:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      // The Enterprise-Grade Fallback UI
      return (
        <div style={{ height: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', backgroundColor: '#f8fafc', padding: '20px', fontFamily: 'system-ui, sans-serif' }}>
          <div style={{ backgroundColor: 'white', padding: '40px', borderRadius: '12px', boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)', maxWidth: '500px', width: '100%', borderTop: '4px solid #ef4444' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '15px', marginBottom: '20px' }}>
              <div style={{ backgroundColor: '#fef2f2', color: '#ef4444', width: '50px', height: '50px', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '24px' }}>
                ⚠️
              </div>
              <div>
                <h2 style={{ margin: 0, color: '#0f172a', fontSize: '1.2rem' }}>Module Crashed</h2>
                <span style={{ color: '#64748b', fontSize: '0.9rem' }}>A critical UI error occurred in this view.</span>
              </div>
            </div>

            <div style={{ backgroundColor: '#f1f5f9', padding: '15px', borderRadius: '6px', fontSize: '11px', color: '#334155', fontFamily: 'monospace', overflowX: 'auto', marginBottom: '25px', border: '1px solid #e2e8f0', maxHeight: '100px' }}>
              {this.state.error && this.state.error.toString()}
            </div>

            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={() => window.location.reload()} 
                className="btn-primary"
              >
                🔄 Reload Application
              </button>
              <button
                onClick={() => {
                  this.setState({ hasError: false, error: null });
                  // Optionally try to force them back to the safe landing page if the app logic allows
                  window.location.href = '/';
                }}
                className="btn-warning"
              >
                Clear State
              </button>
            </div>
          </div>
        </div>
      );
    }

    // If no error, render the children normally
    return this.props.children;
  }
}

export default ErrorBoundary;
