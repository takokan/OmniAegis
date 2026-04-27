-- CreateTable
CREATE TABLE "Threat" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "type" TEXT NOT NULL,
    "riskLevel" TEXT NOT NULL,
    "status" TEXT NOT NULL,
    "sourceURL" TEXT NOT NULL,
    "discoveredAt" DATETIME NOT NULL
);

-- CreateTable
CREATE TABLE "Metric" (
    "id" TEXT NOT NULL PRIMARY KEY,
    "totalAssets" INTEGER NOT NULL,
    "activeThreats" INTEGER NOT NULL,
    "protectionEfficiency" INTEGER NOT NULL
);
