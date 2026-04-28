'use client';

import React, { useState, useRef, useEffect } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { Button } from '../ui/Button';

interface TopNavProps {
  breadcrumb?: Array<{ label: string; href?: string }>;
  onNotificationClick?: () => void;
  notificationCount?: number;
  userName?: string;
  userRole?: 'admin' | 'reviewer';
  onSignOut?: () => Promise<void> | void;
}

/**
 * Top Navigation Bar (56px fixed height)
 * 
 * - Logo on left
 * - Breadcrumb navigation
 * - Search trigger (Cmd+K or /)
 * - Notifications bell
 * - Profile dropdown
 */
export function TopNav({
  breadcrumb,
  onNotificationClick,
  notificationCount = 2,
  userName = 'User',
  userRole,
  onSignOut,
}: TopNavProps) {
  const router = useRouter();
  const [searchOpen, setSearchOpen] = useState(false);
  const [notifOpen, setNotifOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [quickSearch, setQuickSearch] = useState('');
  const notifRef = useRef<HTMLDivElement | null>(null);
  const profileRef = useRef<HTMLDivElement | null>(null);
  const searchRef = useRef<HTMLDivElement | null>(null);

  const quickActions = [
    { label: 'Overview', href: '/' },
    { label: 'Ingest Explorer', href: '/ingest' },
    ...(userRole === 'admin' ? [{ label: 'Model Monitor', href: '/monitor' }] : []),
    { label: 'XAI Viewer', href: '/xai' },
    { label: 'Audit Console', href: '/audit' },
    { label: 'HITL Board', href: '/hitl' },
    { label: 'Blockchain Logs', href: '/blockchain-logs' },
  ].filter((item) => item.label.toLowerCase().includes(quickSearch.toLowerCase()));

  useEffect(() => {
    const handleOutside = (e: MouseEvent) => {
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setProfileOpen(false);
      }
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotifOpen(false);
      }
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setSearchOpen(false);
      }
    };
    document.addEventListener('click', handleOutside);
    return () => document.removeEventListener('click', handleOutside);
  }, []);

  return (
    <header className="fixed top-0 left-0 right-0 h-14 bg-surface-secondary border-b border-border-default z-40 shadow-sm">
      <div className="h-full max-w-[1440px] mx-auto px-4 flex items-center justify-between">
        {/* Left: Logo + Breadcrumb */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2">
            <Link href="/" className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-md bg-accent flex items-center justify-center text-text-primary font-bold text-sm">
                ◆
              </div>
              <span className="font-semibold text-text-primary hidden sm:inline">OmniAegis</span>
            </Link>
          </div>

          {breadcrumb && breadcrumb.length > 0 && (
            <nav className="hidden md:flex items-center gap-2 text-sm text-text-secondary">
              {breadcrumb.map((item, idx) => (
                <React.Fragment key={idx}>
                  {idx > 0 && <span className="text-xs">/</span>}
                  {item.href ? (
                    <a href={item.href} className="hover:text-text-primary transition-colors">
                      {item.label}
                    </a>
                  ) : (
                    <span>{item.label}</span>
                  )}
                </React.Fragment>
              ))}
            </nav>
          )}
        </div>

        {/* Right: Search + Notifications + Profile */}
        <div className="flex items-center gap-3">
          <div className="relative hidden sm:block" ref={searchRef}>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setSearchOpen(!searchOpen)}
              className="text-text-secondary hover:text-text-primary"
              title="Quick navigation"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35" />
                <circle cx="11" cy="11" r="6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              <span className="text-xs normal-case tracking-normal">Quick jump</span>
            </Button>

            {searchOpen && (
              <div className="absolute right-0 mt-2 w-80 rounded-xl border border-border-default bg-surface-secondary p-3 shadow-lg z-50">
                <input
                  value={quickSearch}
                  onChange={(e) => setQuickSearch(e.target.value)}
                  placeholder="Search pages..."
                  className="w-full rounded-lg border border-border-default bg-surface-primary px-3 py-2 text-sm text-text-primary outline-none focus:border-accent"
                />
                <div className="mt-3 space-y-1">
                  {quickActions.length > 0 ? (
                    quickActions.map((item) => (
                      <button
                        key={item.href}
                        onClick={() => {
                          setSearchOpen(false);
                          setQuickSearch('');
                          router.push(item.href);
                        }}
                        className="w-full rounded-lg px-3 py-2 text-left text-sm text-text-secondary hover:bg-surface-tertiary hover:text-text-primary"
                      >
                        {item.label}
                      </button>
                    ))
                  ) : (
                    <p className="px-3 py-2 text-sm text-text-tertiary">No matching pages</p>
                  )}
                </div>
              </div>
            )}
          </div>

          <div className="relative" ref={notifRef}>
            <button
              onClick={() => {
                setNotifOpen((v) => !v);
                onNotificationClick?.();
              }}
              className="relative p-2 rounded-md text-text-secondary hover:text-text-primary hover:bg-surface-tertiary transition-colors"
              aria-label="Notifications"
              title="Notifications"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6 6 0 10-12 0v3.159c0 .538-.214 1.055-.595 1.436L4 17h5" />
                <path strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" d="M13.73 21a2 2 0 01-3.46 0" />
              </svg>
              {notificationCount > 0 && (
                <span className="absolute top-0 right-0 w-5 h-5 bg-danger text-text-primary text-2xs rounded-full flex items-center justify-center font-bold">
                  {notificationCount > 9 ? '9+' : notificationCount}
                </span>
              )}
            </button>

            {notifOpen && (
              <div className="absolute right-0 mt-2 w-72 bg-surface-secondary border border-border-default rounded-xl shadow-md p-3 z-50">
                <p className="text-sm text-text-primary font-semibold">Notifications</p>
                <div className="mt-3 space-y-2 text-xs">
                  <div className="rounded-lg bg-surface-tertiary px-3 py-2 text-text-secondary">
                    XAI service health should be verified before export.
                  </div>
                  <div className="rounded-lg bg-surface-tertiary px-3 py-2 text-text-secondary">
                    2 ingest jobs are still processing.
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="w-px h-6 bg-border-default" />

          <div className="relative" ref={profileRef}>
            <button
              onClick={() => setProfileOpen((v) => !v)}
              className="flex items-center gap-2 px-3 py-2 rounded-md text-text-secondary hover:text-text-primary hover:bg-surface-tertiary transition-colors"
              aria-label="User menu"
            >
              <div className="w-6 h-6 rounded-full bg-accent flex items-center justify-center text-text-primary text-xs font-bold">
                {userName.charAt(0).toUpperCase()}
              </div>
              <span className="hidden sm:inline text-sm">{userName}</span>
            </button>

            {profileOpen && (
              <div className="absolute right-0 mt-2 w-56 bg-surface-secondary border border-border-default rounded-xl shadow-md p-2 z-50">
                <div className="px-3 py-2">
                  <p className="text-sm font-semibold text-text-primary">{userName}</p>
                  <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary mt-1">
                    {userRole || 'guest'}
                  </p>
                </div>
                <div className="my-2 h-px bg-border-default" />
                <button
                  onClick={async () => {
                    setProfileOpen(false);
                    if (onSignOut) {
                      await onSignOut();
                    }
                    router.push('/login');
                  }}
                  className="w-full text-left px-3 py-2 text-sm text-text-primary hover:bg-surface-tertiary rounded"
                >
                  Sign out
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}

export default TopNav;
