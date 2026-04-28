'use client';

import React, { useState, useEffect } from 'react';
import { MainLayout } from '@/components/layout';
import {
  ConfidenceBadge,
  Button,
  Input,
} from '@/components/ui';

function AssetTypeIcon({ type }: { type: HITLTask['assetType'] }) {
  if (type === 'image') {
    return (
      <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="2.5" y="3" width="11" height="10" rx="2" />
        <circle cx="6" cy="6.2" r="1" />
        <path d="m4 11 2.5-2.5L8.6 10l1.4-1.4L12 11" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }

  if (type === 'video') {
    return (
      <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <rect x="2.5" y="3.5" width="7.5" height="9" rx="1.5" />
        <path d="m10 6 3.5-2v8L10 10" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }

  if (type === 'audio') {
    return (
      <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M6.5 5.5v5a1.75 1.75 0 1 1-1-1.58V4.7l6-1.2v4.8a1.75 1.75 0 1 1-1-1.58V2.7l-4 1" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }

  return (
    <svg className="h-3.5 w-3.5" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
      <path d="M4 2.5h5l3 3v8H4z" />
      <path d="M9 2.5v3h3" />
      <path d="M6 8.5h4M6 10.5h4" strokeLinecap="round" />
    </svg>
  );
}

interface HITLTask {
  id: string;
  assetId: string;
  assetType: 'image' | 'video' | 'audio' | 'text';
  description: string;
  confidence: number;
  policy: string;
  priority: 'high' | 'medium' | 'low';
  createdAt: string;
  estimatedReview: string;
}

interface TaskBoard {
  pending: HITLTask[];
  reviewing: HITLTask[];
  approved: HITLTask[];
  rejected: HITLTask[];
}

const INITIAL_TASKS: TaskBoard = {
  pending: [
    {
      id: 'HITL-2024-0501',
      assetId: 'img_a7x2q9p1',
      assetType: 'image',
      description: 'Borderline confidence (0.52) on policy decision',
      confidence: 0.52,
      policy: 'ContentV3',
      priority: 'high',
      createdAt: '2024-04-28 13:22:05',
      estimatedReview: '5 min',
    },
    {
      id: 'HITL-2024-0500',
      assetId: 'vid_b8y3r0q2',
      assetType: 'video',
      description: 'Complex scene with multiple violations',
      confidence: 0.38,
      policy: 'ContentV3',
      priority: 'high',
      createdAt: '2024-04-28 12:45:33',
      estimatedReview: '8 min',
    },
    {
      id: 'HITL-2024-0499',
      assetId: 'aud_c9z4s1r3',
      assetType: 'audio',
      description: 'Ambiguous speech pattern',
      confidence: 0.45,
      policy: 'AudioV1',
      priority: 'medium',
      createdAt: '2024-04-28 11:18:14',
      estimatedReview: '3 min',
    },
    {
      id: 'HITL-2024-0498',
      assetId: 'txt_d0a5t2s4',
      assetType: 'text',
      description: 'Contextual nuance missed by model',
      confidence: 0.41,
      policy: 'NLPv2',
      priority: 'medium',
      createdAt: '2024-04-28 10:52:47',
      estimatedReview: '4 min',
    },
    {
      id: 'HITL-2024-0497',
      assetId: 'img_e1b6u3t5',
      assetType: 'image',
      description: 'Edge case in background analysis',
      confidence: 0.48,
      policy: 'ContentV3',
      priority: 'low',
      createdAt: '2024-04-28 09:30:22',
      estimatedReview: '6 min',
    },
    {
      id: 'HITL-2024-0496',
      assetId: 'vid_f2c7v4u6',
      assetType: 'video',
      description: 'Frame-by-frame review recommended',
      confidence: 0.35,
      policy: 'ContentV3',
      priority: 'high',
      createdAt: '2024-04-28 08:15:11',
      estimatedReview: '12 min',
    },
    {
      id: 'HITL-2024-0495',
      assetId: 'aud_g3d8w5v7',
      assetType: 'audio',
      description: 'Background noise affecting detection',
      confidence: 0.44,
      policy: 'AudioV1',
      priority: 'low',
      createdAt: '2024-04-28 07:41:56',
      estimatedReview: '5 min',
    },
    {
      id: 'HITL-2024-0494',
      assetId: 'txt_h4e9x6w8',
      assetType: 'text',
      description: 'Sarcasm detection boundary',
      confidence: 0.43,
      policy: 'NLPv2',
      priority: 'medium',
      createdAt: '2024-04-28 06:20:14',
      estimatedReview: '4 min',
    },
    {
      id: 'HITL-2024-0493',
      assetId: 'img_i5f0y7x9',
      assetType: 'image',
      description: 'Low resolution artifact',
      confidence: 0.39,
      policy: 'ContentV3',
      priority: 'low',
      createdAt: '2024-04-28 05:08:42',
      estimatedReview: '3 min',
    },
    {
      id: 'HITL-2024-0492',
      assetId: 'vid_j6g1z8y0',
      assetType: 'video',
      description: 'Rapid scene transitions',
      confidence: 0.47,
      policy: 'ContentV3',
      priority: 'medium',
      createdAt: '2024-04-28 04:33:19',
      estimatedReview: '7 min',
    },
  ],
  reviewing: [
    {
      id: 'HITL-2024-0491',
      assetId: 'img_k7h2a1z1',
      assetType: 'image',
      description: 'Model vs. human disagreement',
      confidence: 0.36,
      policy: 'ContentV3',
      priority: 'high',
      createdAt: '2024-04-28 03:15:06',
      estimatedReview: '5 min',
    },
    {
      id: 'HITL-2024-0490',
      assetId: 'aud_l8i3b2a2',
      assetType: 'audio',
      description: 'Emotion vs. intention mismatch',
      confidence: 0.40,
      policy: 'AudioV1',
      priority: 'medium',
      createdAt: '2024-04-28 02:47:53',
      estimatedReview: '3 min',
    },
  ],
  approved: [
    {
      id: 'HITL-2024-0489',
      assetId: 'img_m9j4c3b3',
      assetType: 'image',
      description: 'Model decision confirmed',
      confidence: 0.89,
      policy: 'ContentV3',
      priority: 'low',
      createdAt: '2024-04-27 23:22:11',
      estimatedReview: '2 min',
    },
  ],
  rejected: [
    {
      id: 'HITL-2024-0488',
      assetId: 'txt_n0k5d4c4',
      assetType: 'text',
      description: 'False positive overruled',
      confidence: 0.18,
      policy: 'NLPv2',
      priority: 'low',
      createdAt: '2024-04-27 22:51:45',
      estimatedReview: '3 min',
    },
  ],
};

export default function HITLBoardPage() {
  const [taskBoard, setTaskBoard] = useState<TaskBoard>(INITIAL_TASKS);
  const [selectedTask, setSelectedTask] = useState<HITLTask | null>(null);
  const [selectedColumn, setSelectedColumn] = useState<keyof TaskBoard>('pending');
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [searchTerm, setSearchTerm] = useState('');

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!selectedTask) return;

      // A = Approve
      if (e.key === 'a' || e.key === 'A') {
        approveTask(selectedTask.id);
        setToastMessage(`✓ Approved ${selectedTask.id}`);
      }

      // R = Reject
      if (e.key === 'r' || e.key === 'R') {
        rejectTask(selectedTask.id);
        setToastMessage(`✗ Rejected ${selectedTask.id}`);
      }

      // N = Note (open annotation)
      if (e.key === 'n' || e.key === 'N') {
        setToastMessage(`📝 Opening annotation for ${selectedTask.id}`);
      }

      // → = Next task
      if (e.key === 'ArrowRight') {
        moveToNextTask();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedTask, taskBoard]);

  const approveTask = (taskId: string) => {
    const allTasks = Object.values(taskBoard).flat();
    const task = allTasks.find((t) => t.id === taskId);
    if (!task) return;

    setTaskBoard((prev) => {
      const newBoard = { ...prev };
      for (const key of Object.keys(newBoard) as Array<keyof TaskBoard>) {
        newBoard[key] = newBoard[key].filter((t) => t.id !== taskId);
      }
      newBoard.approved = [...newBoard.approved, task];
      return newBoard;
    });

    const columnTasks = taskBoard[selectedColumn];
    const currentIndex = columnTasks.findIndex((t) => t.id === taskId);
    if (currentIndex < columnTasks.length - 1) {
      setSelectedTask(columnTasks[currentIndex + 1]);
    } else {
      setSelectedTask(null);
    }
  };

  const rejectTask = (taskId: string) => {
    const allTasks = Object.values(taskBoard).flat();
    const task = allTasks.find((t) => t.id === taskId);
    if (!task) return;

    setTaskBoard((prev) => {
      const newBoard = { ...prev };
      for (const key of Object.keys(newBoard) as Array<keyof TaskBoard>) {
        newBoard[key] = newBoard[key].filter((t) => t.id !== taskId);
      }
      newBoard.rejected = [...newBoard.rejected, task];
      return newBoard;
    });

    const columnTasks = taskBoard[selectedColumn];
    const currentIndex = columnTasks.findIndex((t) => t.id === taskId);
    if (currentIndex < columnTasks.length - 1) {
      setSelectedTask(columnTasks[currentIndex + 1]);
    } else {
      setSelectedTask(null);
    }
  };

  const moveToNextTask = () => {
    if (!selectedTask) {
      const firstTask = taskBoard.pending[0];
      if (firstTask) {
        setSelectedTask(firstTask);
        setSelectedColumn('pending');
      }
      return;
    }

    const columnTasks = taskBoard[selectedColumn];
    const currentIndex = columnTasks.findIndex((t) => t.id === selectedTask.id);
    if (currentIndex < columnTasks.length - 1) {
      setSelectedTask(columnTasks[currentIndex + 1]);
    }
  };

  const filteredTasks = Object.fromEntries(
    Object.entries(taskBoard).map(([key, tasks]) => [
      key,
      tasks.filter(
        (task) =>
          searchTerm === '' ||
          task.id.toLowerCase().includes(searchTerm.toLowerCase()) ||
          task.assetId.toLowerCase().includes(searchTerm.toLowerCase()),
      ),
    ]),
  ) as TaskBoard;

  const totalPending = filteredTasks.pending.length;
  const totalReviewing = filteredTasks.reviewing.length;

  const Column = ({
    title,
    status,
    tasks,
    accentColor,
  }: {
    title: string;
    status: keyof TaskBoard;
    tasks: HITLTask[];
    accentColor: string;
  }) => (
    <section className="snap-start flex flex-col rounded-2xl bg-surface-secondary shadow-[0_10px_28px_rgba(16,24,40,0.08)] overflow-hidden border border-border-subtle">
      <header className="sticky top-0 z-10 px-4 py-3 bg-surface-tertiary/95 backdrop-blur supports-[backdrop-filter]:bg-surface-tertiary/80 border-b border-border-subtle">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${accentColor}`} />
          <h3 className="text-sm font-semibold text-text-primary">{title}</h3>
          <span className="ml-auto inline-flex items-center rounded-full bg-surface-elevated px-2 py-0.5 text-xs font-semibold text-text-secondary">
            {tasks.length}
          </span>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto max-h-[calc(100vh-320px)]">
        {tasks.length === 0 ? (
          <div className="p-4 text-center text-text-tertiary text-sm">
            No tasks
          </div>
        ) : (
          <div className="space-y-2 p-3">
            {tasks.map((task) => (
              <div
                key={task.id}
                onClick={() => {
                  setSelectedTask(task);
                  setSelectedColumn(status);
                }}
                className={`p-3 rounded-xl cursor-pointer border transition-colors duration-150 ease-out ${
                  selectedTask?.id === task.id
                    ? 'bg-surface-elevated border-accent/30 shadow-[0_0_0_1px_rgba(108,99,255,0.22),0_10px_24px_rgba(108,99,255,0.10)]'
                    : 'bg-surface-tertiary border-border-subtle hover:bg-surface-tertiary/80 hover:border-border-subtle hover:shadow-sm'
                }`}
              >
                <div className="flex items-start justify-between gap-2 mb-2">
                  <code className="text-xs font-mono text-accent">{task.id}</code>
                  <span
                    className={`px-2 py-1 rounded text-xs font-semibold ${
                      task.priority === 'high'
                        ? 'bg-danger bg-opacity-20 text-danger'
                        : task.priority === 'medium'
                          ? 'bg-warning bg-opacity-20 text-warning'
                          : 'bg-border-subtle text-text-secondary'
                    }`}
                  >
                    {task.priority}
                  </span>
                </div>

                <p className="text-xs text-text-secondary mb-2">{task.description}</p>

                <div className="flex items-center justify-between gap-2 mb-2">
                  <span className="inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs font-semibold bg-surface-secondary text-text-secondary shadow-sm">
                    <AssetTypeIcon type={task.assetType} />
                    {task.assetType.toUpperCase()}
                  </span>
                  <ConfidenceBadge value={task.confidence} size="sm" />
                </div>

                <p className="text-xs text-text-tertiary">{task.estimatedReview}</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );

  return (
    <MainLayout
      breadcrumb={[{ label: 'HITL Board' }]}
      contextPanelTitle={selectedTask ? selectedTask.id : 'Task Details'}
      contextPanelContent={
        selectedTask && (
          <div className="space-y-6">
            {/* Task Header */}
            <div className="space-y-3">
              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Task ID
                </p>
                <p className="text-sm font-mono text-accent">{selectedTask.id}</p>
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Description
                </p>
                <p className="text-sm text-text-primary">{selectedTask.description}</p>
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
                  Priority
                </p>
                <span
                  className={`px-3 py-1 rounded text-xs font-semibold ${
                    selectedTask.priority === 'high'
                      ? 'bg-danger bg-opacity-20 text-danger'
                      : selectedTask.priority === 'medium'
                        ? 'bg-warning bg-opacity-20 text-warning'
                        : 'bg-border-subtle text-text-secondary'
                  }`}
                >
                  {selectedTask.priority.toUpperCase()}
                </span>
              </div>
            </div>

            {/* Asset Info */}
            <div className="border-t border-border-subtle pt-4 space-y-3">
              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Asset
                </p>
                <div className="flex items-center gap-2">
                  <span className="px-2 py-1 rounded text-xs font-semibold bg-surface-tertiary text-text-secondary">
                    {selectedTask.assetType.toUpperCase()}
                  </span>
                  <code className="text-xs font-mono text-text-secondary">
                    {selectedTask.assetId}
                  </code>
                </div>
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
                  Model Confidence
                </p>
                <ConfidenceBadge value={selectedTask.confidence} showTooltip />
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Policy
                </p>
                <p className="text-sm text-text-primary">{selectedTask.policy}</p>
              </div>
            </div>

            {/* Timestamps */}
            <div className="border-t border-border-subtle pt-4 space-y-2">
              <div>
                <p className="text-xs text-text-tertiary">Created {selectedTask.createdAt}</p>
              </div>
            </div>

            {/* Keyboard Shortcuts */}
            <div className="border-t border-border-subtle pt-4 bg-surface-tertiary rounded-md p-3 space-y-2">
              <p className="text-xs font-semibold text-text-secondary uppercase letter-spacing-wide mb-3">
                Keyboard Shortcuts
              </p>
              <div className="space-y-2 text-xs">
                <div className="flex justify-between">
                  <span className="text-text-secondary">Approve</span>
                  <kbd className="px-2 py-1 bg-surface-secondary border border-border-default rounded font-mono text-accent">
                    A
                  </kbd>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Reject</span>
                  <kbd className="px-2 py-1 bg-surface-secondary border border-border-default rounded font-mono text-accent">
                    R
                  </kbd>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Annotate</span>
                  <kbd className="px-2 py-1 bg-surface-secondary border border-border-default rounded font-mono text-accent">
                    N
                  </kbd>
                </div>
                <div className="flex justify-between">
                  <span className="text-text-secondary">Next Task</span>
                  <kbd className="px-2 py-1 bg-surface-secondary border border-border-default rounded font-mono text-accent">
                    →
                  </kbd>
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="border-t border-border-subtle pt-4 space-y-2">
              <Button
                size="sm"
                className="w-full"
                onClick={() => approveTask(selectedTask.id)}
              >
                Approve (A)
              </Button>
              <Button
                variant="danger"
                size="sm"
                className="w-full"
                onClick={() => rejectTask(selectedTask.id)}
              >
                Reject (R)
              </Button>
              <Button variant="secondary" size="sm" className="w-full">
                Annotate (N)
              </Button>
            </div>
          </div>
        )
      }
      contextPanelActions={
        selectedTask && (
          <Button variant="secondary" size="sm" onClick={() => setSelectedTask(null)}>
            Close
          </Button>
        )
      }
      isContextPanelOpen={!!selectedTask}
      onContextPanelClose={() => setSelectedTask(null)}
    >
      {/* Main Content */}
      <div className="space-y-6">
        {/* Page Header */}
        <div className="space-y-4">
          <div>
            <h1 className="text-4xl font-bold text-text-primary">HITL Board</h1>
            <p className="text-lg text-text-secondary mt-1">
              Review tasks flagged for human-in-the-loop approval
            </p>
          </div>

          {/* Quick Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div className="rounded-2xl bg-surface-secondary border border-border-subtle p-4 shadow-sm">
              <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold">
                Pending
              </p>
              <p className="text-2xl font-bold text-danger mt-1">{totalPending}</p>
            </div>
            <div className="rounded-2xl bg-surface-secondary border border-border-subtle p-4 shadow-sm">
              <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold">
                Reviewing
              </p>
              <p className="text-2xl font-bold text-warning mt-1">{totalReviewing}</p>
            </div>
            <div className="rounded-2xl bg-surface-secondary border border-border-subtle p-4 shadow-sm">
              <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold">
                Approved
              </p>
              <p className="text-2xl font-bold text-success mt-1">{filteredTasks.approved.length}</p>
            </div>
            <div className="rounded-2xl bg-surface-secondary border border-border-subtle p-4 shadow-sm">
              <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold">
                Rejected
              </p>
              <p className="text-2xl font-bold text-danger mt-1">{filteredTasks.rejected.length}</p>
            </div>
          </div>
        </div>

        {/* Search */}
        <div className="rounded-2xl bg-surface-secondary border border-border-subtle p-4">
          <Input
            label="Search Tasks"
            placeholder="Audit ID, Asset ID..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        {/* Kanban Board */}
        <div className="rounded-2xl bg-surface-primary border border-border-subtle p-3 md:p-4">
          <div className="flex items-center justify-between gap-3 mb-3">
            <div className="text-sm font-semibold text-text-primary">Queue</div>
            <div className="text-xs text-text-tertiary">
              Tip: use <kbd className="px-1.5 py-0.5 bg-surface-secondary border border-border-default rounded font-mono text-accent">A</kbd>{' '}
              / <kbd className="px-1.5 py-0.5 bg-surface-secondary border border-border-default rounded font-mono text-accent">R</kbd>{' '}
              to approve/reject, <kbd className="px-1.5 py-0.5 bg-surface-secondary border border-border-default rounded font-mono text-accent">→</kbd>{' '}
              for next
            </div>
          </div>

          <div className="-mx-3 md:-mx-4 px-3 md:px-4 overflow-x-auto pb-2">
            <div className="flex gap-4 min-w-[1080px] xl:min-w-0 xl:grid xl:grid-cols-4 xl:gap-4">
              <div className="w-[260px] sm:w-[280px] lg:w-[300px] xl:w-auto">
                <Column
                  title="Pending"
                  status="pending"
                  tasks={filteredTasks.pending}
                  accentColor="bg-danger"
                />
              </div>
              <div className="w-[260px] sm:w-[280px] lg:w-[300px] xl:w-auto">
                <Column
                  title="Reviewing"
                  status="reviewing"
                  tasks={filteredTasks.reviewing}
                  accentColor="bg-warning"
                />
              </div>
              <div className="w-[260px] sm:w-[280px] lg:w-[300px] xl:w-auto">
                <Column
                  title="Approved"
                  status="approved"
                  tasks={filteredTasks.approved}
                  accentColor="bg-success"
                />
              </div>
              <div className="w-[260px] sm:w-[280px] lg:w-[300px] xl:w-auto">
                <Column
                  title="Rejected"
                  status="rejected"
                  tasks={filteredTasks.rejected}
                  accentColor="bg-danger"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Toast */}
      {toastMessage && (
        <div className="fixed bottom-6 right-6 px-4 py-3 rounded-lg bg-accent text-text-primary text-sm font-medium shadow-lg">
          {toastMessage}
        </div>
      )}
    </MainLayout>
  );
}
