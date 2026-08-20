import { Link } from 'react-router-dom';
import { Starfield } from '@/components/features/explore/Starfield';

export default function NotFound() {
  return (
    <div className="relative min-h-screen flex items-center justify-center px-6 overflow-hidden bg-space-950">
      <Starfield className="absolute inset-0" density={160} />
      <div className="relative text-center max-w-md">
        <p className="font-mono text-2xs uppercase tracking-[0.3em] text-accent-cyan/70 mb-4">
          Signal lost
        </p>
        <h1 className="font-display text-4xl font-bold text-space-100 mb-3">404</h1>
        <p className="text-sm text-space-400 mb-8 leading-relaxed">
          There is nothing at this address. It may have moved, or the link may be wrong.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3">
          <Link
            to="/"
            className="h-9 px-4 inline-flex items-center rounded-md text-sm bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/30 hover:bg-accent-cyan/20 transition-colors focus-ring"
          >
            Back to start
          </Link>
          <Link
            to="/explore"
            className="h-9 px-4 inline-flex items-center rounded-md text-sm bg-space-800 text-space-200 border border-space-700 hover:bg-space-700 transition-colors focus-ring"
          >
            Explore space
          </Link>
        </div>
      </div>
    </div>
  );
}
