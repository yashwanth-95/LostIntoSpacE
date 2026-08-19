import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useDebounce } from '@/hooks/useDebounce';

interface SearchModalProps {
  open: boolean;
  onClose: () => void;
}

export function SearchModal({ open, onClose }: SearchModalProps) {
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebounce(query, 250);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (open) {
      setTimeout(() => inputRef.current?.focus(), 50);
    } else {
      setQuery('');
    }
  }, [open]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) {
      navigate(`/search?q=${encodeURIComponent(query.trim())}`);
      onClose();
    }
  };

  if (!open) return null;

  // Placeholder suggestions
  const suggestions = debouncedQuery.length > 0
    ? [
        { label: `Search for "${debouncedQuery}"`, type: 'query' as const },
        { label: `Ask AI about "${debouncedQuery}"`, type: 'ai' as const },
      ]
    : [
        { label: 'International Space Station', type: 'object' as const },
        { label: 'Orbital mechanics course', type: 'lesson' as const },
        { label: 'Apollo 11 mission', type: 'mission' as const },
        { label: 'Merlin engine specifications', type: 'component' as const },
      ];

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-[15vh] bg-black/60 backdrop-blur-sm animate-fade-in"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl mx-4 glass-panel shadow-2xl overflow-hidden animate-slide-up"
        onClick={(e) => e.stopPropagation()}
      >
        <form onSubmit={handleSubmit}>
          <div className="flex items-center gap-3 px-4 border-b border-space-800">
            <svg className="w-4 h-4 text-space-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
            </svg>
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search space objects, missions, lessons..."
              className="flex-1 h-12 bg-transparent text-sm text-space-100 placeholder:text-space-500 outline-none"
            />
            <kbd className="text-2xs text-space-500 border border-space-700 rounded px-1.5 py-0.5">Esc</kbd>
          </div>
        </form>

        <div className="py-2 max-h-[40vh] overflow-y-auto">
          {suggestions.map((s, i) => (
            <button
              key={i}
              className="flex items-center gap-3 w-full px-4 py-2.5 text-sm text-space-300 hover:bg-space-800 hover:text-space-100 transition-colors text-left"
              onClick={() => {
                if (s.type === 'ai') {
                  navigate(`/assistant?q=${encodeURIComponent(debouncedQuery)}`);
                } else if (s.type === 'query') {
                  navigate(`/search?q=${encodeURIComponent(debouncedQuery)}`);
                } else {
                  navigate(`/search?q=${encodeURIComponent(s.label)}`);
                }
                onClose();
              }}
            >
              <span className="text-2xs text-space-500 uppercase w-16 shrink-0 text-right">
                {s.type}
              </span>
              <span>{s.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
