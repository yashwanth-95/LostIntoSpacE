import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { Button, Card, Input } from '@/components/ui';
import { auth } from '@/services/api';
import { useAuthStore } from '@/stores/authStore';
import { Starfield } from '@/components/features/explore/Starfield';

/**
 * Create an account.
 *
 * The password rule is stated up front rather than only after a rejection: the
 * backend enforces a minimum length, and discovering that by failing is a poor
 * first interaction.
 */
export default function Signup() {
  const navigate = useNavigate();
  const login = useAuthStore((s) => s.login);
  const continueAsGuest = useAuthStore((s) => s.continueAsGuest);

  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setPending(true);
    setError(null);
    try {
      const tokens = await auth.register({ name, email, password });
      login(tokens.user ?? null, tokens.access_token, tokens.refresh_token);
      if (!tokens.user) {
        try {
          useAuthStore.getState().setUser(await auth.me());
        } catch {
          /* the session is valid even if the profile fetch fails */
        }
      }
      navigate('/workspace', { replace: true });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not create the account.');
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="relative min-h-[calc(100vh-3.5rem)] flex items-center justify-center px-6 py-12 overflow-hidden">
      <Starfield className="absolute inset-0" density={120} />
      <Card className="relative w-full max-w-sm space-y-5">
        <div>
          <h1 className="font-display text-xl font-semibold text-space-100 mb-1">
            Create an account
          </h1>
          <p className="text-xs text-space-400">
            To save rockets, missions, simulations and learning progress.
          </p>
        </div>

        <form onSubmit={submit} className="space-y-3">
          <label className="block">
            <span className="text-2xs text-space-500 block mb-1">Name</span>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              autoComplete="name"
            />
          </label>

          <label className="block">
            <span className="text-2xs text-space-500 block mb-1">Email</span>
            <Input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoComplete="email"
            />
          </label>

          <label className="block">
            <span className="text-2xs text-space-500 block mb-1">Password</span>
            <Input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              autoComplete="new-password"
            />
            <span className="text-2xs text-space-600 mt-1 block">At least 8 characters.</span>
          </label>

          {error && (
            <p className="text-2xs text-severity-fatal leading-relaxed" role="alert">
              {error}
            </p>
          )}

          <Button type="submit" className="w-full" loading={pending}>
            Create account
          </Button>
        </form>

        <div className="space-y-2 border-t border-space-800 pt-4">
          <p className="text-2xs text-space-500">
            Already have one?{' '}
            <Link to="/login" className="text-accent-cyan hover:underline">
              Sign in
            </Link>
          </p>
          <button
            onClick={() => {
              continueAsGuest();
              navigate('/explore');
            }}
            className="text-2xs text-space-500 hover:text-space-300 transition-colors focus-ring rounded"
          >
            Or continue as a guest — everything except saving works →
          </button>
        </div>
      </Card>
    </div>
  );
}
