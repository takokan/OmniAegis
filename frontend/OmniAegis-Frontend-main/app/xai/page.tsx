'use client';

import { MainLayout } from '@/components/layout';
import XAIRelationshipExplorer from '@/components/XAIRelationshipExplorer';

export default function XAIViewerPage() {
  return (
    <MainLayout
      breadcrumb={[{ label: 'XAI Viewer' }]}
      contextPanelTitle="Graph Details"
      contextPanelContent={null}
      contextPanelActions={null}
      isContextPanelOpen={false}
      onContextPanelClose={() => undefined}
    >
      <XAIRelationshipExplorer />
    </MainLayout>
  );
}
