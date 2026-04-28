'use client';

import React, { useState, useMemo, useEffect } from 'react';
import { useAuth } from '@/lib/auth-context';
import { MainLayout } from '@/components/layout';
import { Button, Input, DataTable } from '@/components/ui';

interface IngestItem {
  id: string;
  filename: string;
  mediaType: 'image' | 'video' | 'audio' | 'text';
  size: string;
  status: 'processing' | 'completed' | 'failed' | 'pending';
  progress: number;
  uploadedAt: string;
  processedAt?: string;
  errorMessage?: string;
}

const DEMO_ITEMS: IngestItem[] = [
  {
    id: 'INV-2024-001',
    filename: 'product_photo_001.jpg',
    mediaType: 'image',
    size: '2.4 MB',
    status: 'completed',
    progress: 100,
    uploadedAt: '2024-04-28 14:05:22',
    processedAt: '2024-04-28 14:05:45',
  },
  {
    id: 'INV-2024-002',
    filename: 'interview_video_042.mp4',
    mediaType: 'video',
    size: '156 MB',
    status: 'processing',
    progress: 67,
    uploadedAt: '2024-04-28 13:52:11',
  },
  {
    id: 'INV-2024-003',
    filename: 'podcast_episode_18.m4a',
    mediaType: 'audio',
    size: '45 MB',
    status: 'completed',
    progress: 100,
    uploadedAt: '2024-04-28 13:30:00',
    processedAt: '2024-04-28 13:45:33',
  },
  {
    id: 'INV-2024-004',
    filename: 'customer_feedback.txt',
    mediaType: 'text',
    size: '0.8 MB',
    status: 'pending',
    progress: 0,
    uploadedAt: '2024-04-28 13:15:44',
  },
  {
    id: 'INV-2024-005',
    filename: 'user_generated_content.jpg',
    mediaType: 'image',
    size: '3.1 MB',
    status: 'completed',
    progress: 100,
    uploadedAt: '2024-04-28 12:58:19',
    processedAt: '2024-04-28 12:58:56',
  },
  {
    id: 'INV-2024-006',
    filename: 'livestream_archive.mp4',
    mediaType: 'video',
    size: '512 MB',
    status: 'processing',
    progress: 42,
    uploadedAt: '2024-04-28 12:32:05',
  },
  {
    id: 'INV-2024-007',
    filename: 'support_transcript.txt',
    mediaType: 'text',
    size: '1.2 MB',
    status: 'failed',
    progress: 100,
    uploadedAt: '2024-04-28 11:45:22',
    errorMessage: 'Encoding detection failed: UTF-8 parse error',
  },
  {
    id: 'INV-2024-008',
    filename: 'dataset_batch_3.zip',
    mediaType: 'image',
    size: '89 MB',
    status: 'completed',
    progress: 100,
    uploadedAt: '2024-04-28 11:20:00',
    processedAt: '2024-04-28 11:28:14',
  },
];

const getStatusColor = (status: string) => {
  switch (status) {
    case 'completed':
      return 'bg-success bg-opacity-10 text-success';
    case 'processing':
      return 'bg-warning bg-opacity-10 text-warning';
    case 'failed':
      return 'bg-danger bg-opacity-10 text-danger';
    case 'pending':
      return 'bg-border-subtle text-text-secondary';
    default:
      return 'bg-border-subtle text-text-secondary';
  }
};

export default function IngestExplorerPage() {
  const [selectedItem, setSelectedItem] = useState<IngestItem | null>(null);
  const [viewMode, setViewMode] = useState<'grid' | 'list'>('list');
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<string | null>(null);
  const { user } = useAuth();
  const [items, setItems] = useState<IngestItem[]>(DEMO_ITEMS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const fetchItems = async () => {
      if (!user) return;
      setLoading(true);
      setError(null);
      try {
        const token = localStorage.getItem('sentinel-access-token') || '';
        const res = await fetch(`/api/ingest?userId=${encodeURIComponent(user.id)}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
        if (!res.ok) throw new Error(`Server returned ${res.status}`);
        const payload = await res.json();
        if (!cancelled && Array.isArray(payload)) {
          setItems(payload as IngestItem[]);
        }
      } catch (err) {
        // keep demo data but surface a non-blocking error
        if (!cancelled) setError((err as Error).message || 'Failed to load ingest items');
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    fetchItems();
    return () => {
      cancelled = true;
    };
  }, [user]);

  const filteredItems = useMemo(() => {
    return items.filter((item) => {
      const matchesSearch =
        searchTerm === '' ||
        item.filename.toLowerCase().includes(searchTerm.toLowerCase()) ||
        item.id.toLowerCase().includes(searchTerm.toLowerCase());

      const matchesStatus = !filterStatus || item.status === filterStatus;
      const matchesType = !filterType || item.mediaType === filterType;

      return matchesSearch && matchesStatus && matchesType;
    });
  }, [items, searchTerm, filterStatus, filterType]);

  const statusOptions = [...new Set(items.map((i) => i.status))];
  const typeOptions = [...new Set(items.map((i) => i.mediaType))];

  const stats = {
    total: items.length,
    completed: items.filter((i) => i.status === 'completed').length,
    processing: items.filter((i) => i.status === 'processing').length,
    failed: items.filter((i) => i.status === 'failed').length,
  };

  return (
    <MainLayout
      breadcrumb={[{ label: 'Ingest Explorer' }]}
      contextPanelTitle={selectedItem ? selectedItem.id : 'Item Details'}
      contextPanelContent={
        selectedItem && (
          <div className="space-y-6">
            {/* Item Header */}
            <div className="space-y-3">
              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Ingest ID
                </p>
                <p className="text-sm font-mono text-accent">{selectedItem.id}</p>
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Filename
                </p>
                <p className="text-sm text-text-primary break-all">{selectedItem.filename}</p>
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Type
                </p>
                <span className="px-2 py-1 rounded text-xs font-semibold bg-surface-tertiary text-text-secondary">
                  {selectedItem.mediaType.toUpperCase()}
                </span>
              </div>
            </div>

            {/* Status & Progress */}
            <div className="border-t border-border-subtle pt-4 space-y-3">
              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
                  Status
                </p>
                <span className={`px-3 py-1 rounded text-xs font-semibold ${getStatusColor(selectedItem.status)}`}>
                  {selectedItem.status.toUpperCase()}
                </span>
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
                  Progress
                </p>
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-text-secondary">Processing</span>
                    <span className="text-text-primary font-semibold">{selectedItem.progress}%</span>
                  </div>
                  <div className="w-full h-2 bg-surface-tertiary rounded-full overflow-hidden">
                    <div
                      className={`h-full transition-all duration-normal ${
                        selectedItem.status === 'completed'
                          ? 'bg-success'
                          : selectedItem.status === 'processing'
                            ? 'bg-warning'
                            : selectedItem.status === 'failed'
                              ? 'bg-danger'
                              : 'bg-border-default'
                      }`}
                      style={{ width: `${selectedItem.progress}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* File Info */}
            <div className="border-t border-border-subtle pt-4 space-y-3">
              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  File Size
                </p>
                <p className="text-sm text-text-primary font-mono">{selectedItem.size}</p>
              </div>

              <div>
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                  Uploaded
                </p>
                <p className="text-xs text-text-secondary font-mono">{selectedItem.uploadedAt}</p>
              </div>

              {selectedItem.processedAt && (
                <div>
                  <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-1">
                    Processed
                  </p>
                  <p className="text-xs text-text-secondary font-mono">{selectedItem.processedAt}</p>
                </div>
              )}
            </div>

            {/* Error Message */}
            {selectedItem.errorMessage && (
              <div className="border-t border-border-subtle pt-4 bg-danger bg-opacity-10 border border-danger border-opacity-30 rounded-md p-3">
                <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
                  Error
                </p>
                <p className="text-xs text-danger font-mono">{selectedItem.errorMessage}</p>
              </div>
            )}

            <div className="border-t border-border-subtle pt-4">
              <p className="text-xs text-text-tertiary">
                Detailed ingest actions will appear here once the ingest workflow API is connected.
              </p>
            </div>
          </div>
        )
      }
      contextPanelActions={selectedItem ? <Button variant="secondary" size="sm" onClick={() => setSelectedItem(null)}>Close</Button> : null}
      isContextPanelOpen={!!selectedItem}
      onContextPanelClose={() => setSelectedItem(null)}
    >
      {/* Main Content */}
      <div className="space-y-6">
        {/* Page Header */}
        <div className="space-y-2">
          <h1 className="text-4xl font-bold text-text-primary">Ingest Explorer</h1>
          <p className="text-lg text-text-secondary">
            Monitor and manage ingested media, processing status, and pipeline health
          </p>
        </div>

        {/* Statistics */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="p-4 rounded-lg bg-surface-secondary shadow-sm">
            <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
              Total Ingested
            </p>
            <p className="text-3xl font-bold text-text-primary">{stats.total}</p>
          </div>

          <div className="p-4 rounded-lg bg-surface-secondary shadow-sm">
            <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
              Completed
            </p>
            <p className="text-3xl font-bold text-success">{stats.completed}</p>
          </div>

          <div className="p-4 rounded-lg bg-surface-secondary shadow-sm">
            <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
              Processing
            </p>
            <p className="text-3xl font-bold text-warning">{stats.processing}</p>
          </div>

          <div className="p-4 rounded-lg bg-surface-secondary shadow-sm">
            <p className="text-xs text-text-secondary uppercase letter-spacing-wide font-semibold mb-2">
              Failed
            </p>
            <p className="text-3xl font-bold text-danger">{stats.failed}</p>
          </div>
        </div>

        {(loading || error) && (
          <div className="rounded-xl bg-surface-secondary px-4 py-3 shadow-sm">
            <p className="text-xs uppercase tracking-[0.18em] text-text-tertiary">Data source</p>
            <p className="mt-2 text-sm text-text-primary">
              {loading
                ? `Loading ingest records for ${user?.id || 'current user'}...`
                : `Live ingest API is unavailable for ${user?.id || 'current user'}, so this page is using fallback demo data.`}
            </p>
            {error && <p className="mt-2 text-xs text-text-tertiary">Request error: {error}</p>}
          </div>
        )}

        {/* Filters */}
        <div className="p-4 bg-surface-secondary rounded-lg space-y-4 shadow-sm">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
            <Input
              label="Search Items"
              placeholder="Filename, ID..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />

            <div>
              <label className="block text-xs font-semibold text-text-secondary uppercase letter-spacing-wide mb-2">
                Status
              </label>
              <select
                value={filterStatus || ''}
                onChange={(e) => setFilterStatus(e.target.value || null)}
                className="w-full px-3 py-2 rounded-md border border-border-default bg-surface-primary text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent"
              >
                <option value="">All Statuses</option>
                {statusOptions.map((status) => (
                  <option key={status} value={status}>
                    {status.charAt(0).toUpperCase() + status.slice(1)}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-text-secondary uppercase letter-spacing-wide mb-2">
                Type
              </label>
              <select
                value={filterType || ''}
                onChange={(e) => setFilterType(e.target.value || null)}
                className="w-full px-3 py-2 rounded-md border border-border-default bg-surface-primary text-text-primary text-sm focus:outline-none focus:ring-2 focus:ring-accent"
              >
                <option value="">All Types</option>
                {typeOptions.map((type) => (
                  <option key={type} value={type}>
                    {type.charAt(0).toUpperCase() + type.slice(1)}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex gap-2">
              <Button
                variant={viewMode === 'list' ? 'primary' : 'secondary'}
                size="md"
                onClick={() => setViewMode('list')}
              >
                List
              </Button>
              <Button
                variant={viewMode === 'grid' ? 'primary' : 'secondary'}
                size="md"
                onClick={() => setViewMode('grid')}
              >
                Grid
              </Button>
            </div>
          </div>

          <p className="text-xs text-text-tertiary">
            {filteredItems.length} of {items.length} items
          </p>
        </div>

        {/* List View */}
        {viewMode === 'list' && (
          <DataTable<IngestItem>
            columns={[
              {
                key: 'id',
                label: 'ID',
                sortable: true,
                width: '140px',
                render: (val) => (
                  <code className="text-xs font-mono text-accent">{val}</code>
                ),
              },
              {
                key: 'filename',
                label: 'Filename',
                sortable: true,
                render: (val) => <span className="text-sm text-text-primary truncate">{val}</span>,
              },
              {
                key: 'mediaType',
                label: 'Type',
                sortable: true,
                width: '100px',
                render: (val) => (
                  <span className="px-2 py-1 rounded text-xs font-semibold bg-surface-tertiary text-text-secondary">
                    {val.toUpperCase()}
                  </span>
                ),
              },
              {
                key: 'size',
                label: 'Size',
                sortable: true,
                width: '120px',
                render: (val) => <span className="text-xs text-text-secondary">{val}</span>,
              },
              {
                key: 'status',
                label: 'Status',
                sortable: true,
                render: (val) => (
                  <span className={`px-2 py-1 rounded text-xs font-semibold ${getStatusColor(val)}`}>
                    {val.toUpperCase()}
                  </span>
                ),
              },
              {
                key: 'progress',
                label: 'Progress',
                sortable: true,
                width: '140px',
                render: (val) => (
                  <div className="flex items-center gap-2">
                    <div className="flex-1 h-2 bg-surface-tertiary rounded-full overflow-hidden">
                      <div
                        className="h-full bg-accent"
                        style={{ width: `${val}%` }}
                      />
                    </div>
                    <span className="text-xs text-text-secondary w-10">{val}%</span>
                  </div>
                ),
              },
              {
                key: 'uploadedAt',
                label: 'Uploaded',
                sortable: true,
                render: (val) => <span className="text-xs text-text-tertiary">{val}</span>,
              },
            ]}
            rows={filteredItems}
            onRowClick={(row) => setSelectedItem(row)}
          />
        )}

        {/* Grid View */}
        {viewMode === 'grid' && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {filteredItems.map((item) => (
              <div
                key={item.id}
                onClick={() => setSelectedItem(item)}
                className="p-4 rounded-lg bg-surface-secondary hover:bg-surface-tertiary cursor-pointer transition-colors duration-fast shadow-sm"
              >
                <div className="flex items-start justify-between mb-3">
                  <code className="text-xs font-mono text-accent">{item.id}</code>
                  <span className={`px-2 py-1 rounded text-xs font-semibold ${getStatusColor(item.status)}`}>
                    {item.status.toUpperCase()}
                  </span>
                </div>

                <p className="text-sm text-text-primary truncate mb-2 font-semibold">
                  {item.filename}
                </p>

                <div className="space-y-2 mb-3">
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-text-secondary">{item.mediaType}</span>
                    <span className="text-text-secondary">{item.size}</span>
                  </div>
                  <div className="w-full h-2 bg-surface-tertiary rounded-full overflow-hidden">
                    <div
                      className="h-full bg-accent"
                      style={{ width: `${item.progress}%` }}
                    />
                  </div>
                  <p className="text-xs text-text-tertiary">{item.uploadedAt}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </MainLayout>
  );
}
