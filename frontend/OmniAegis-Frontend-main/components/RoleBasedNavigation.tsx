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
    <aside className="space-y-4 rounded-3xl border border-slate-200/70 bg-slate-50/80 p-6 shadow-sm">
      <div className="space-y-1">
        <p className="text-xs uppercase tracking-[0.32em] text-slate-400">Navigation</p>
        <p className="text-sm font-semibold text-slate-600 mt-2 mb-4">
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
                  ? 'bg-slate-950/5 text-slate-900'
                  : 'text-slate-600 hover:bg-slate-950/5 hover:text-slate-900'
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </div>

      {/* User Info & Logout */}
      <div className="border-t border-slate-200 pt-4 mt-6 space-y-3">
        <div className="text-sm">
          <p className="text-xs uppercase tracking-[0.28em] text-slate-400">Logged in as</p>
          <p className="font-semibold text-slate-900 mt-1">{user.name}</p>
          <p className="text-xs text-slate-500">{user.email}</p>
        </div>
        <button
          onClick={logout}
          className="w-full rounded-2xl bg-slate-200 hover:bg-slate-300 text-slate-900 font-semibold py-2 text-sm transition"
        >
          Sign out
        </button>
      </div>
    </aside>
  );
}