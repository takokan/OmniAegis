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
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
        <div className="w-full max-w-md">
          {/* Background glow effect */}
          <div className="absolute inset-x-0 top-0 h-72 bg-gradient-to-b from-blue-500/10 via-transparent to-transparent pointer-events-none" />

          <div className="relative space-y-8">
            {/* Header */}
            <div className="text-center space-y-4">
              <div className="inline-flex items-center justify-center h-12 w-12 rounded-full bg-accent/10">
                <span className="text-xl font-bold text-accent">◆</span>
              </div>
              <div className="space-y-2">
                <h1 className="text-3xl font-bold tracking-tight text-slate-950">SentinelAgent</h1>
                <p className="text-sm text-slate-600">Brand Protection & IP Monitoring Command Center</p>
              </div>
            </div>

            {/* Auth Card */}
            <div className="rounded-[2rem] border border-slate-200/80 bg-white/95 shadow-soft backdrop-blur-xl p-8 space-y-6">
              <div className="grid grid-cols-2 rounded-2xl border border-slate-200 bg-slate-50 p-1">
                <button
                  type="button"
                  onClick={() => {
                    setMode('login');
                    setError('');
                  }}
                  className={`rounded-xl px-4 py-2 text-sm font-semibold transition ${
                    mode === 'login' ? 'bg-white text-slate-900 shadow' : 'text-slate-500 hover:text-slate-700'
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
                    mode === 'signup' ? 'bg-white text-slate-900 shadow' : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  Sign up
                </button>
              </div>

              <form onSubmit={handleSubmit} className="space-y-5">
                {/* Name Field */}
                {mode === 'signup' && (
                  <div className="space-y-2">
                    <label htmlFor="name" className="text-sm font-semibold text-slate-900">
                      Full Name
                    </label>
                    <input
                      id="name"
                      type="text"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                      placeholder="Jane Doe"
                      className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition"
                      required
                    />
                  </div>
                )}

                {/* Email Field */}
                <div className="space-y-2">
                  <label htmlFor="email" className="text-sm font-semibold text-slate-900">
                    Email
                  </label>
                  <input
                    id="email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition"
                    required
                  />
                </div>

                {/* Password Field */}
                <div className="space-y-2">
                  <label htmlFor="password" className="text-sm font-semibold text-slate-900">
                    Password
                  </label>
                  <input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition"
                    required
                  />
                </div>

                {/* Error Message */}
                {error && (
                  <div className="rounded-2xl bg-red-50 border border-red-200 p-3 text-sm text-red-700">
                    {error}
                  </div>
                )}

                {/* Submit Button */}
                <input
                  type="submit"
                  disabled={isLoading}
                  className="w-full rounded-2xl bg-accent hover:bg-accent/90 disabled:bg-slate-300 text-white font-semibold py-3 transition shadow-lg shadow-accent/20 cursor-pointer"
                  value={isLoading ? 'Processing...' : mode === 'login' ? 'Sign in' : 'Create account'}
                />

                <div className="relative py-1">
                  <div className="absolute inset-0 flex items-center">
                    <div className="w-full border-t border-slate-200" />
                  </div>
                  <div className="relative flex justify-center">
                    <span className="bg-white px-3 text-xs uppercase tracking-[0.2em] text-slate-400">or</span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleGoogleAuth}
                  disabled={isLoading}
                  className="w-full rounded-2xl border border-slate-200 bg-white hover:bg-slate-50 disabled:bg-slate-100 text-slate-700 font-semibold py-3 transition flex items-center justify-center gap-3"
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
                <div className="border-t border-slate-200 pt-6 space-y-3">
                  <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Demo Credentials</p>
                  <div className="space-y-2 text-sm">
                    <div className="rounded-2xl bg-slate-50 p-3">
                      <p className="font-mono text-slate-600">
                        <span className="text-slate-400">Admin:</span> admin@sentinelai.com / admin123
                      </p>
                    </div>
                    <div className="rounded-2xl bg-slate-50 p-3">
                      <p className="font-mono text-slate-600">
                        <span className="text-slate-400">Reviewer:</span> reviewer@sentinelai.com / reviewer123
                      </p>
                    </div>
                  </div>
                </div>
              )}

              {mode === 'signup' && (
                <p className="text-xs text-slate-500">
                  Sign up creates a reviewer account by default. Admin role remains restricted.
                </p>
              )}
            </div>

            {/* Footer */}
            <p className="text-center text-xs text-slate-500">
              Secure authentication with role-based access control
            </p>
          </div>
        </div>
      </div>
  );
}