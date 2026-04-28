'use client';

import React from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';

interface NavItem {
  label: string;
  href: string;
  icon: 'overview' | 'ingest' | 'monitor' | 'xai' | 'audit' | 'hitl';
  badge?: number;
  children?: NavItem[];
}

interface SidebarProps {
  items: NavItem[];
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
}

const defaultItems: NavItem[] = [
  { label: 'Overview', href: '/', icon: 'overview' },
  { label: 'Ingest Explorer', href: '/ingest', icon: 'ingest' },
  { label: 'Model Monitor', href: '/monitor', icon: 'monitor' },
  { label: 'XAI Viewer', href: '/xai', icon: 'xai' },
  { label: 'Audit Console', href: '/audit', icon: 'audit', badge: 0 },
  { label: 'HITL Board', href: '/hitl', icon: 'hitl', badge: 0 },
];

function NavIcon({ icon, active }: { icon: NavItem['icon']; active: boolean }) {
  const className = `h-4 w-4 ${active ? 'text-accent' : 'text-text-secondary group-hover:text-text-primary'}`;

  switch (icon) {
    case 'overview':
      return (
        <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M3 10.5 10 4l7 6.5" />
          <path d="M5.5 9.5V16h9V9.5" />
        </svg>
      );
    case 'ingest':
      return (
        <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M10 3v8" />
          <path d="m6.5 8.5 3.5 3.5 3.5-3.5" />
          <path d="M4 15.5h12" />
        </svg>
      );
    case 'monitor':
      return (
        <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M3 15.5h14" />
          <path d="M5 12.5 8 9l2.5 2 4-5" />
        </svg>
      );
    case 'xai':
      return (
        <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8">
          <circle cx="9" cy="9" r="4.5" />
          <path d="m12.5 12.5 3 3" />
        </svg>
      );
    case 'audit':
      return (
        <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8">
          <path d="M6 3.5h8v13H6z" />
          <path d="M8 7h4M8 10h4M8 13h3" />
        </svg>
      );
    case 'hitl':
      return (
        <svg className={className} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8">
          <circle cx="7" cy="7" r="2.5" />
          <circle cx="13" cy="7" r="2.5" />
          <path d="M3.5 15c.7-2 2-3 3.5-3s2.8 1 3.5 3" />
          <path d="M9.5 15c.7-2 2-3 3.5-3s2.8 1 3.5 3" />
        </svg>
      );
  }
}

/**
 * Sidebar navigation (240px fixed, collapses to 64px)
 * 
 * - Fixed position with badge counts
 * - Collapsed state shows icons only
 * - Active item highlighted with accent color + muted background
 * - Keyboard accessible
 */
export function Sidebar({
  items = defaultItems,
  collapsed = false,
  onCollapsedChange,
}: SidebarProps) {
  const pathname = usePathname();

  const normalizePath = (p: string) => {
    if (!p) return '/';
    if (p === '/') return '/';
    return p.endsWith('/') ? p.slice(0, -1) : p;
  };

  const isActive = (href: string) => {
    const current = normalizePath(pathname || '/');
    const target = normalizePath(href);

    // Root should only match root (otherwise it matches everything)
    if (target === '/') return current === '/';

    // Exact match, or "section match" for nested routes like /hitl/queue
    return current === target || current.startsWith(`${target}/`);
  };

  const renderNavItem = (item: NavItem, depth = 0) => {
    const active = isActive(item.href);

    return (
    <div key={item.href} className={collapsed ? 'flex justify-center' : undefined}>
      <Link
        href={item.href}
        title={collapsed ? item.label : undefined}
        className={`relative flex items-center rounded-xl text-sm font-medium transition-all duration-fast group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 ${
          collapsed ? 'w-10 justify-center px-0 py-2' : 'justify-between px-3 py-2.5'
        } ${
          active
            ? 'bg-accent-muted text-text-primary shadow-[inset_0_0_0_1px_rgba(108,99,255,0.24)]'
            : 'text-text-secondary hover:text-text-primary hover:bg-surface-tertiary'
        }`}
        style={{
          paddingLeft: collapsed ? undefined : `${12 + depth * 12}px`,
        }}
      >
        <div className={`flex items-center ${collapsed ? 'justify-center' : 'gap-2 min-w-0'}`}>
          <span className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-surface-primary/40">
            <NavIcon icon={item.icon} active={active} />
          </span>
          {!collapsed && (
            <span className="truncate text-xs">{item.label}</span>
          )}
        </div>
        {item.badge !== undefined && item.badge > 0 && !collapsed && (
          <span className="ml-auto flex-shrink-0 px-2 py-0.5 rounded-full bg-danger text-text-primary text-2xs font-bold">
            {item.badge > 9 ? '9+' : item.badge}
          </span>
        )}
        {item.badge !== undefined && item.badge > 0 && collapsed && (
          <span
            className="absolute top-0.5 right-0.5 w-4 h-4 rounded-full bg-danger text-text-primary text-2xs flex items-center justify-center font-bold"
          >
            {item.badge}
          </span>
        )}
      </Link>
    </div>
    );
  };

  return (
    <aside
      className={`fixed left-0 top-14 h-[calc(100vh-56px)] border-r border-border-default bg-surface-secondary overflow-y-auto transition-all duration-normal z-30 ${
        collapsed ? 'w-16' : 'w-60'
      }`}
    >
      <div className={`${collapsed ? 'p-2' : 'p-3'} space-y-4`}>
        {/* Main Nav */}
        <nav className="space-y-1">
          {items.map((item) => renderNavItem(item))}
        </nav>

        <div className="h-px bg-border-default" />

        {/* Footer Actions */}
        <nav className="space-y-1">
          <button
            onClick={() => onCollapsedChange?.(!collapsed)}
            className={`w-full flex items-center rounded-md text-sm text-text-secondary hover:text-text-primary hover:bg-surface-tertiary transition-colors ${
              collapsed ? 'justify-center px-2 py-2' : 'gap-2 px-3 py-2'
            }`}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <span className="text-base">{collapsed ? '→' : '←'}</span>
            {!collapsed && <span className="text-xs">Collapse</span>}
          </button>
        </nav>
      </div>
    </aside>
  );
}

export default Sidebar;
