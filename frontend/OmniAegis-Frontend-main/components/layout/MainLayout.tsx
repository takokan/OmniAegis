'use client';

import React, { ReactNode, useMemo, useState } from 'react';
import { TopNav } from './TopNav';
import { Sidebar } from './Sidebar';
import { ContextPanel } from './ContextPanel';
import { useAuth } from '@/lib/auth-context';

interface MainLayoutProps {
  children: ReactNode;
  breadcrumb?: Array<{ label: string; href?: string }>;
  contextPanelTitle?: string;
  contextPanelContent?: ReactNode;
  contextPanelActions?: ReactNode;
  isContextPanelOpen?: boolean;
  onContextPanelClose?: () => void;
}

/**
 * Main layout shell
 * 
 * Combines:
 * - Fixed top nav (56px)
 * - Left sidebar (240px, collapsible to 64px)
 * - Main content area (max-width 1440px)
 * - Right context panel (380px slide-in)
 */
export function MainLayout({
  children,
  breadcrumb,
  contextPanelTitle = 'Details',
  contextPanelContent,
  contextPanelActions,
  isContextPanelOpen = false,
  onContextPanelClose,
}: MainLayoutProps) {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const { user, logout } = useAuth();

  const navItems = useMemo(
    () => {
      const items = [
        { label: 'Overview', href: '/', icon: 'overview' as const },
        { label: 'Ingest Explorer', href: '/ingest', icon: 'ingest' as const },
        user?.role === 'admin'
          ? { label: 'Model Monitor', href: '/monitor', icon: 'monitor' as const }
          : null,
        { label: 'XAI Viewer', href: '/xai', icon: 'xai' as const },
        { label: 'Audit Console', href: '/audit', icon: 'audit' as const, badge: 3 },
        { label: 'HITL Board', href: '/hitl', icon: 'hitl' as const, badge: 12 },
        { label: 'Blockchain Logs', href: '/blockchain-logs', icon: 'blockchain' as const, badge: 0 },
      ];

      return items.filter((item): item is NonNullable<(typeof items)[number]> => Boolean(item));
    },
    [user?.role],
  );

  return (
    <div className="min-h-screen bg-surface-primary text-text-primary">
      {/* Top Navigation */}
      <TopNav
        breadcrumb={breadcrumb}
        userName={user?.name || 'Guest'}
        userRole={user?.role}
        onSignOut={user ? logout : undefined}
      />

      <div className="flex pt-14">
        {/* Sidebar */}
        <Sidebar
          items={navItems}
          collapsed={sidebarCollapsed}
          onCollapsedChange={setSidebarCollapsed}
        />

        {/* Main Content */}
        <main
          className={`flex-1 transition-all duration-normal ${
            sidebarCollapsed ? 'ml-16' : 'ml-60'
          }`}
        >
          <div className="max-w-container mx-auto px-8 py-8">
            {children}
          </div>
        </main>
      </div>

      {/* Context Panel (Right Slide-In) */}
      {contextPanelContent && (
        <ContextPanel
          isOpen={isContextPanelOpen}
          onClose={onContextPanelClose || (() => {})}
          title={contextPanelTitle}
          actions={contextPanelActions}
        >
          {contextPanelContent}
        </ContextPanel>
      )}
    </div>
  );
}

export default MainLayout;
