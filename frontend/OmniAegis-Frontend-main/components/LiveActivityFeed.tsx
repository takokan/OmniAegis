'use client';

import { useEffect, useState } from 'react';

const feedItems = [
  'New suspicious artwork detected on social media.',
  'High-risk counterfeit listing discovered in marketplace scan.',
  'A logo infringement case was escalated for expert review.',
  'System completed brand asset integrity sweep.',
  'Pending threat queue refreshed with latest entries.',
];

export default function LiveActivityFeed() {
  const [items, setItems] = useState<string[]>([]);

  useEffect(() => {
    setItems(feedItems);
  }, []);

  return (
    <section className="premium-card rounded-[2rem] p-8 backdrop-blur-sm">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="text-sm uppercase tracking-[0.28em] text-text-tertiary">Live activity</p>
          <h2 className="mt-3 text-2xl font-bold text-text-primary">Latest discoveries</h2>
        </div>
        <span className="rounded-full bg-surface-elevated px-4 py-2 text-sm font-semibold text-text-secondary">Live feed</span>
      </div>
      <div className="mt-8 space-y-4 text-text-secondary">
        {items.map((item) => (
          <div key={item} className="rounded-3xl bg-surface-elevated p-5 text-sm leading-7 shadow-sm">
            {item}
          </div>
        ))}
      </div>
    </section>
  );
}