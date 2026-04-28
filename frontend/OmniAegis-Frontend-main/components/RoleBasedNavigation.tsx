'use client';

import { useAuth } from '@/lib/auth-context';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

export default function RoleBasedNavigation() {
  const { user, logout } = useAuth();
  const pathname = usePathname();

  if (!user) return null;

  // Define navigation items based on role
  const navItems = [
    { href: '/', label: 'Executive Command Center', roles: ['admin', 'reviewer'] },
    { href: '/rl-optimizer', label: 'RL Optimizer', roles: ['admin'] },
    { href: '/hitl-queue', label: 'HITL Operational Queue', roles: ['reviewer'] },
    { href: '/governance', label: 'System Governance', roles: ['admin'] },
  ];

  const visibleItems = navItems.filter((item) => item.roles.includes(user.role));

  return (
    <aside className="premium-card space-y-4 rounded-3xl p-6">
      <div className="space-y-1">
        <p className="text-xs uppercase tracking-[0.32em] text-text-tertiary">Navigation</p>
        <p className="text-sm font-semibold text-text-secondary mt-2 mb-4">
          {user.role === 'admin' ? '👨‍💼 Admin' : '👁️ Reviewer'}
        </p>
      </div>
      <div className="space-y-2">
        {visibleItems.map((item) => {
          const isActive = pathname === item.href;
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`block rounded-2xl px-4 py-3 text-sm font-semibold transition ${
                isActive
                  ? 'bg-surface-elevated text-text-primary'
                  : 'text-text-secondary hover:bg-surface-elevated hover:text-text-primary'
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </div>

      {/* User Info & Logout */}
      <div className="pt-4 mt-6 space-y-3">
        <div className="text-sm">
          <p className="text-xs uppercase tracking-[0.28em] text-text-tertiary">Logged in as</p>
          <p className="font-semibold text-text-primary mt-1">{user.name}</p>
          <p className="text-xs text-text-secondary">{user.email}</p>
        </div>
        <button
          onClick={logout}
          className="w-full rounded-2xl bg-surface-elevated hover:bg-accent/10 text-text-primary font-semibold py-2 text-sm transition"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}