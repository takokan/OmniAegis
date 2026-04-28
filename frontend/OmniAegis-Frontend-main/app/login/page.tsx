'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { useRouter } from 'next/navigation';

export default function LoginPage() {
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const { login, signup, loginWithGoogle, signupWithGoogle } = useAuth();
  const router = useRouter();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    try {
      if (mode === 'login') {
        await login(email, password);
      } else {
        await signup(name, email, password);
      }
      router.push('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Authentication failed. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleGoogleAuth = async () => {
    setError('');
    setIsLoading(true);

    try {
      if (mode === 'login') {
        await loginWithGoogle();
      } else {
        await signupWithGoogle();
      }
      router.push('/');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Google authentication failed.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen bg-surface-primary flex items-center justify-center p-4">
        <div className="w-full max-w-md">
          {/* Background glow effect */}
          <div className="absolute inset-x-0 top-0 h-72 bg-gradient-to-b from-accent/15 via-transparent to-transparent pointer-events-none" />

          <div className="relative space-y-8">
            {/* Header */}
            <div className="text-center space-y-4">
              <div className="inline-flex items-center justify-center h-12 w-12 rounded-full bg-accent/10">
                <span className="text-xl font-bold text-accent">◆</span>
              </div>
              <div className="space-y-2">
                <h1 className="text-3xl font-bold tracking-tight text-text-primary">SentinelAgent</h1>
                <p className="text-sm text-text-secondary">Brand Protection & IP Monitoring Command Center</p>
              </div>
            </div>

            {/* Auth Card */}
            <div className="rounded-[2rem] bg-surface-secondary shadow-md p-8 space-y-6">
              <div className="grid grid-cols-2 rounded-2xl bg-surface-tertiary p-1">
                <button
                  type="button"
                  onClick={() => {
                    setMode('login');
                    setError('');
                  }}
                  className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${
                    mode === 'login' ? 'bg-surface-elevated text-text-primary shadow' : 'text-text-secondary hover:text-text-primary'
                  }`}
                >
                  Login
                </button>
                <button
                  type="button"
                  onClick={() => {
                    setMode('signup');
                    setError('');
                  }}
                  className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${
                    mode === 'signup' ? 'bg-surface-elevated text-text-primary shadow' : 'text-text-secondary hover:text-text-primary'
                  }`}
                >
                  Sign up
                </button>
              </div>

              <form onSubmit={handleSubmit} className="space-y-5">
                {/* Name Field */}
                {mode === 'signup' && (
                  <div className="space-y-2">
                    <label htmlFor="name" className="text-sm font-semibold text-text-primary">
                      Full Name
                    </label>
                    <input
                      id="name"
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Jane Doe"
                      className="w-full rounded-2xl border border-border-default bg-surface-primary px-4 py-3 text-text-primary placeholder-text-tertiary focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition"
                      required
                    />
                  </div>
                )}

                {/* Email Field */}
                <div className="space-y-2">
                  <label htmlFor="email" className="text-sm font-semibold text-text-primary">
                    {mode === 'login' ? 'Email or Username' : 'Email'}
                  </label>
                  <input
                    id="email"
                    type={mode === 'login' ? 'text' : 'email'}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder={mode === 'login' ? 'you@example.com or admin' : 'you@example.com'}
                    className="w-full rounded-2xl border border-border-default bg-surface-primary px-4 py-3 text-text-primary placeholder-text-tertiary focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition"
                    required
                  />
                </div>

                {/* Password Field */}
                <div className="space-y-2">
                  <label htmlFor="password" className="text-sm font-semibold text-text-primary">
                    Password
                  </label>
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full rounded-2xl border border-border-default bg-surface-primary px-4 py-3 text-text-primary placeholder-text-tertiary focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition"
                    required
                  />
                </div>

                {/* Error Message */}
                {error && (
                  <div className="rounded-2xl bg-danger-bg border border-danger/30 p-3 text-sm text-danger">
                    {error}
                  </div>
                )}

                {/* Submit Button */}
                <input
                  type="submit"
                  disabled={isLoading}
                  className="w-full rounded-2xl bg-accent hover:bg-accent/90 disabled:bg-surface-tertiary text-text-primary font-semibold py-3 transition shadow-lg shadow-accent/20 cursor-pointer"
                  value={isLoading ? 'Processing...' : mode === 'login' ? 'Sign in' : 'Create account'}
                />

                <div className="relative py-1">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-border-default" />
                  </div>
                  <div className="relative flex justify-center">
                    <span className="bg-surface-secondary px-3 text-xs uppercase tracking-[0.2em] text-text-secondary">or</span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleGoogleAuth}
                  disabled={isLoading}
                  className="w-full rounded-2xl border border-border-default bg-surface-primary hover:bg-surface-tertiary disabled:bg-surface-tertiary text-text-primary font-semibold py-3 transition flex items-center justify-center gap-3"
                >
                  <svg className="h-5 w-5" viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      fill="#EA4335"
                      d="M12 11.8v4.7h6.6c-.3 1.5-1.8 4.3-6.6 4.3-4 0-7.2-3.3-7.2-7.3s3.2-7.3 7.2-7.3c2.3 0 3.8 1 4.7 1.8l3.2-3.1C17.7 2.9 15.1 2 12 2 6.5 2 2 6.5 2 12s4.5 10 10 10c5.8 0 9.6-4.1 9.6-9.8 0-.7-.1-1.2-.2-1.7H12z"
                    />
                  </svg>
                  {mode === 'login' ? 'Continue with Google' : 'Sign up with Google'}
                </button>
              </form>

              {/* Demo Credentials */}
              {mode === 'login' && (
                <div className="border-t border-border-default pt-6 space-y-3">
                  <p className="text-xs uppercase tracking-[0.28em] text-text-tertiary">Demo Credentials</p>
                  <div className="space-y-2 text-sm">
                    <div className="rounded-2xl bg-surface-primary p-3">
                      <p className="font-mono text-text-secondary">
                        <span className="text-text-tertiary">Admin:</span> admin@sentinelai.com / admin123 (or admin / password)
                      </p>
                    </div>
                    <div className="rounded-2xl bg-surface-primary p-3">
                      <p className="font-mono text-text-secondary">
                        <span className="text-text-tertiary">Reviewer:</span> reviewer@sentinelai.com / reviewer123 (or reviewer / password)
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {mode === 'signup' && (
                <p className="text-xs text-text-tertiary">
                  Sign up creates a reviewer account by default. Admin role remains restricted.
                </p>
              )}
            </div>

            {/* Footer */}
            <p className="text-center text-xs text-text-tertiary">
              Secure authentication with role-based access control
            </p>
          </div>
        </div>
      </div>
  );
}