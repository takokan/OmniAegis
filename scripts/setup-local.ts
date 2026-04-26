import { ethers } from "hardhat";

/**
 * Local development setup script
 * Deploys contracts to local hardhat network and sets up gateways
 */

async function main() {
  const [deployer, gateway1, gateway2, user1, user2] = await ethers.getSigners();

  console.log("🚀 Setting up OmniAegis for local development...\n");

  // Deploy MerkleAnchor
  console.log("📝 Deploying MerkleAnchor...");
  const MerkleAnchor = await ethers.getContractFactory("MerkleAnchor");
  const merkleAnchor = await MerkleAnchor.deploy(deployer.address);
  await merkleAnchor.waitForDeployment();
  const merkleAnchorAddr = await merkleAnchor.getAddress();
  console.log("✓ MerkleAnchor:", merkleAnchorAddr);

  // Deploy PolicyRegistry
  console.log("\n📝 Deploying PolicyRegistry...");
  const PolicyRegistry = await ethers.getContractFactory("PolicyRegistry");
  const guardians = [gateway1.address, gateway2.address, user1.address];
  const policyRegistry = await PolicyRegistry.deploy(deployer.address, guardians);
  await policyRegistry.waitForDeployment();
  const policyRegistryAddr = await policyRegistry.getAddress();
  console.log("✓ PolicyRegistry:", policyRegistryAddr);
  console.log("  Guardians:", guardians);

  // Deploy SentinelAudit
  console.log("\n📝 Deploying SentinelAudit...");
  const SentinelAudit = await ethers.getContractFactory("SentinelAudit");
  const sentinelAudit = await SentinelAudit.deploy(deployer.address);
  await sentinelAudit.waitForDeployment();
  const sentinelAuditAddr = await sentinelAudit.getAddress();
  console.log("✓ SentinelAudit:", sentinelAuditAddr);

  // Setup gateway authorizations
  console.log("\n🔐 Setting up gateway authorizations...");
  await merkleAnchor.setGatewayAuthorisation(gateway1.address, true);
  await merkleAnchor.setGatewayAuthorisation(gateway2.address, true);
  console.log("✓ MerkleAnchor gateways authorized:", gateway1.address, gateway2.address);

  await sentinelAudit.setGatewayAuthorisation(gateway1.address, true);
  await sentinelAudit.setGatewayAuthorisation(gateway2.address, true);
  console.log("✓ SentinelAudit gateways authorized:", gateway1.address, gateway2.address);

  // Test data
  console.log("\n🧪 Creating test data...");

  // Create a test Merkle batch
  const testRoot = ethers.keccak256(ethers.toBeHex("test-batch-1", 32));
  const testCID = "QmTestCIDForBatch1234567890abcdef";

  const batchTx = await merkleAnchor
    .connect(gateway1)
    .anchorBatch(testRoot, BigInt(0), 10, testCID);
  await batchTx.wait();
  console.log("✓ Test batch anchored with root:", testRoot);

  // Create a test audit decision
  const decisionId = ethers.id("test-decision-1");
  const policyId = BigInt(1);
  const riskScore = 5000; // basis points
  const action = 1; // enforcement action
  const evidenceCID = "QmTestCIDForDecision1234567890abcd";

  const decisionTx = await sentinelAudit
    .connect(gateway1)
    .recordDecision(decisionId, policyId, riskScore, action, true, evidenceCID);
  await decisionTx.wait();
  console.log("✓ Test decision recorded with ID:", decisionId);

  // Display environment variables
  console.log("\n📋 Environment variables for .env:");
  console.log(`MERKLE_ANCHOR_CONTRACT=${merkleAnchorAddr}`);
  console.log(`POLICY_REGISTRY_CONTRACT=${policyRegistryAddr}`);
  console.log(`SENTINEL_AUDIT_CONTRACT=${sentinelAuditAddr}`);
  console.log(`GATEWAY_ADDRESS=${gateway1.address}`);
  console.log(`GATEWAY_SIGNER_ADDRESS=${gateway2.address}`);

  console.log("\n✅ Local development setup complete!");
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error("❌ Setup failed:", error);
    process.exit(1);
  });
