import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/lib/auth-context';

export const metadata: Metadata = {
  title: 'OmniAegis Sentinel',
  description: 'Brand protection and IP monitoring dashboard',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900">
        <AuthProvider>
          <div className="relative isolate overflow-hidden">
            <div className="pointer-events-none absolute inset-x-0 top-0 h-72 bg-top-glow opacity-70" />
            <div className="relative mx-auto max-w-screen-2xl px-4 py-6 sm:px-6 lg:px-8">
              {children}
            </div>
          </div>
        </AuthProvider>
      </body>
    </html>
  );
}