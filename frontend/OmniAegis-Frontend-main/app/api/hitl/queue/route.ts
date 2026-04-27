import { NextResponse } from 'next/server';

// Mock HITL queue data
export async function GET() {
  const queueItems = [
    {
      id: 'hitl_001',
      type: 'Logo',
      riskLevel: 'High',
      status: 'Pending',
      sourceURL: 'https://marketplace.example.com/suspicious-logo',
      discoveredAt: '2026-04-25T14:32:00Z',
      confidenceScore: 0.87,
      reasonCode: 'COUNTERFEIT_TRADEMARK',
      explanation: {
        saliencyMap: 'url_to_saliency_map',
        nodeLinks: 'url_to_relationship_graph',
      },
      context: {
        previousActions: 2,
        seller: 'seller_xyz',
        region: 'US',
      },
    },
    {
      id: 'hitl_002',
      type: 'Artwork',
      riskLevel: 'Med',
      status: 'Pending',
      sourceURL: 'https://social.example.com/post/art-copy',
      discoveredAt: '2026-04-25T12:15:00Z',
      confidenceScore: 0.72,
      reasonCode: 'COPYRIGHT_INFRINGEMENT',
      explanation: {
        saliencyMap: 'url_to_saliency_map',
        nodeLinks: 'url_to_relationship_graph',
      },
      context: {
        previousActions: 0,
        seller: 'user_abc',
        region: 'EU',
      },
    },
    {
      id: 'hitl_003',
      type: 'Counterfeit',
      riskLevel: 'High',
      status: 'Pending',
      sourceURL: 'https://ecommerce.example.com/product/fake',
      discoveredAt: '2026-04-25T10:47:00Z',
      confidenceScore: 0.91,
      reasonCode: 'PRODUCT_COUNTERFEIT',
      explanation: {
        saliencyMap: 'url_to_saliency_map',
        nodeLinks: 'url_to_relationship_graph',
      },
      context: {
        previousActions: 5,
        seller: 'seller_def',
        region: 'APAC',
      },
    },
  ];

  return NextResponse.json({ items: queueItems, total: queueItems.length });
}