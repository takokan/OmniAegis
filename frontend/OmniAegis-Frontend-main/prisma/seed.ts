const { PrismaClient } = require('@prisma/client');

const prisma = new PrismaClient();

async function main() {
  await prisma.metric.deleteMany();
  await prisma.threat.deleteMany();

  await prisma.metric.create({
    data: {
      totalAssets: 2148,
      activeThreats: 18,
      protectionEfficiency: 92,
    },
  });

  const threats = [
    {
      type: 'Logo',
      riskLevel: 'High',
      status: 'Pending',
      sourceURL: 'https://marketplace.example.com/suspicious-logo-asset',
      discoveredAt: new Date(Date.now() - 1000 * 60 * 60 * 2).toISOString(),
    },
    {
      type: 'Artwork',
      riskLevel: 'Med',
      status: 'Pending',
      sourceURL: 'https://social.example.com/post/brand-art-copy',
      discoveredAt: new Date(Date.now() - 1000 * 60 * 60 * 8).toISOString(),
    },
    {
      type: 'Counterfeit',
      riskLevel: 'High',
      status: 'Pending',
      sourceURL: 'https://ecommerce.example.com/product/knockoff-item',
      discoveredAt: new Date(Date.now() - 1000 * 60 * 60 * 24).toISOString(),
    },
    {
      type: 'Logo',
      riskLevel: 'Low',
      status: 'Whitelisted',
      sourceURL: 'https://blog.example.com/approved-brand-mashup',
      discoveredAt: new Date(Date.now() - 1000 * 60 * 60 * 30).toISOString(),
    },
    {
      type: 'Artwork',
      riskLevel: 'Med',
      status: 'Escalated',
      sourceURL: 'https://forum.example.com/copyright-claim-thread',
      discoveredAt: new Date(Date.now() - 1000 * 60 * 60 * 48).toISOString(),
    },
    {
      type: 'Counterfeit',
      riskLevel: 'High',
      status: 'Takedown',
      sourceURL: 'https://auction.example.com/fake-collection',
      discoveredAt: new Date(Date.now() - 1000 * 60 * 60 * 60).toISOString(),
    },
  ];

  for (const threat of threats) {
    await prisma.threat.create({ data: threat });
  }
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });