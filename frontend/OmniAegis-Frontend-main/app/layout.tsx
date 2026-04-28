import type { Metadata } from 'next';
import './globals.css';
import { AuthProvider } from '@/lib/auth-context';

export const metadata: Metadata = {
  title: 'OmniAegis - ML Audit & Explainability Platform',
  description: 'Enterprise ML auditing, explainability, and policy compliance platform',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="light">
      <head>
        <meta name="theme-color" content="#F5F6FA" />
      </head>
      <body className="min-h-screen bg-surface-primary text-text-primary">
        <AuthProvider>
          {children}
        </AuthProvider>
      </body>
    </html>
  );
}