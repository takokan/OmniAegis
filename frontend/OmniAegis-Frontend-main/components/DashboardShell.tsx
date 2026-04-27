'use client';

import { ReactNode } from 'react';
import RoleBasedNavigation from './RoleBasedNavigation';
import ProtectedLayout from './ProtectedLayout';

export default function DashboardShell({ children }: { children: ReactNode }) {
  return (
    <ProtectedLayout>
      <div className="min-h-screen rounded-[2rem] border border-slate-200/80 bg-white/90 shadow-soft backdrop-blur-xl">
        <div className="flex flex-col gap-8 p-6 lg:p-8">
          <header className="flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
            <div className="space-y-3">
              <p className="text-sm uppercase tracking-[0.32em] text-slate-400">Sentinel Agent</p>
              <div className="max-w-2xl space-y-3">
                <h1 className="text-4xl font-bold tracking-tight text-slate-950 sm:text-5xl">OmniAegis Dashboard</h1>
                <p className="text-base leading-8 text-slate-600">
                  Monitor brand protection threats, evaluate risk, and take action from one clean command center.
                </p>
              </div>
            </div>
            <div className="flex flex-col gap-4 rounded-3xl border border-slate-200/70 bg-slate-50/80 p-4 shadow-sm">
              <span className="text-sm uppercase tracking-[0.3em] text-slate-500">Live status</span>
              <div className="flex items-center gap-3 text-slate-900">
                <span className="h-3 w-3 rounded-full bg-emerald-500 shadow-sm" />
                <span className="font-semibold">Real-time monitoring active</span>
              </div>
            </div>
          </header>
          <div className="grid gap-6 lg:grid-cols-[230px_1fr]">
            <RoleBasedNavigation />
            <main className="space-y-8">{children}</main>
          </div>
        </div>
      </div>
    </ProtectedLayout>
  );
}