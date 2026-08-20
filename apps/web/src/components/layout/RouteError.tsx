import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Catches a render-time crash and shows something recoverable.
 *
 * Without a boundary, one thrown error in one page unmounts the entire tree and
 * the user gets a blank white screen with no way back. A class component is
 * still the only way to do this in React 18 — there is no hook equivalent.
 *
 * The message is shown because this is a development-facing prototype and a
 * silent failure is worse than an ugly one. A production build should log this
 * to a service and show only the recovery action.
 */
export class RouteError extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Unhandled render error:', error, info.componentStack);
  }

  render() {
    const { error } = this.state;
    if (!error) return <>{this.props.children}</>;

    return (
      <div className="min-h-screen flex items-center justify-center bg-space-950 p-6">
        <div className="glass-panel p-8 max-w-lg space-y-4">
          <h1 className="font-display text-lg text-space-100">Something went wrong</h1>
          <p className="text-sm text-space-400">
            This screen hit an unexpected error. Nothing was saved or lost — reloading should
            get you back.
          </p>
          <pre className="text-2xs text-severity-critical bg-space-950/70 border border-space-800 rounded p-3 overflow-x-auto">
            {error.message}
          </pre>
          <div className="flex gap-2">
            <button
              onClick={() => window.location.reload()}
              className="h-9 px-4 rounded-md text-sm bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/30 hover:bg-accent-cyan/20 transition-colors"
            >
              Reload
            </button>
            <a
              href="/"
              className="h-9 px-4 rounded-md text-sm inline-flex items-center bg-space-800 text-space-200 border border-space-700 hover:bg-space-700 transition-colors"
            >
              Back to start
            </a>
          </div>
        </div>
      </div>
    );
  }
}
