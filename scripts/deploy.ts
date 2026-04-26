import { ethers, upgrades } from "hardhat";
import * as fs from "fs";
import * as path from "path";

/**
 * Deploy script for OmniAegis smart contracts
 * Deploys all three contracts to the target network
 */

interface DeploymentAddresses {
  merkleAnchor: string;
  policyRegistry: string;
  sentinelAudit: string;
  network: string;
  deployer: string;
  timestamp: number;
}

async function saveBuildArtifacts(): Promise<void> {
  const artifactDir = path.join(__dirname, "../artifacts/contracts");
  const deploymentDir = path.join(__dirname, "../deployments");

  if (!fs.existsSync(deploymentDir)) {
    fs.mkdirSync(deploymentDir);
  }

  if (fs.existsSync(artifactDir)) {
    const files = fs.readdirSync(artifactDir);
    for (const file of files) {
      if (file.endsWith(".json") && !file.includes(".dbg")) {
        const source = path.join(artifactDir, file);
        const dest = path.join(deploymentDir, file);
        fs.copyFileSync(source, dest);
      }
    }
  }

  console.log("✓ Build artifacts saved to deployments/");
}

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("Deploying contracts with account:", deployer.address);
  console.log("Account balance:", (await deployer.getBalance()).toString());

  const network = (await ethers.provider.getNetwork()).name;
  console.log("Network:", network);

  const addresses: DeploymentAddresses = {
    merkleAnchor: "",
    policyRegistry: "",
    sentinelAudit: "",
    network,
    deployer: deployer.address,
    timestamp: Date.now(),
  };

  try {
    // Deploy MerkleAnchor
    console.log("\n📝 Deploying MerkleAnchor...");
    const MerkleAnchor = await ethers.getContractFactory("MerkleAnchor");
    const merkleAnchor = await MerkleAnchor.deploy(deployer.address);
    await merkleAnchor.waitForDeployment();
    addresses.merkleAnchor = await merkleAnchor.getAddress();
    console.log("✓ MerkleAnchor deployed to:", addresses.merkleAnchor);

    // Deploy PolicyRegistry
    console.log("\n📝 Deploying PolicyRegistry...");
    const PolicyRegistry = await ethers.getContractFactory("PolicyRegistry");
    const guardians = [
      deployer.address,
      deployer.address, // In production, use different addresses
      deployer.address, // In production, use different addresses
    ];
    const policyRegistry = await PolicyRegistry.deploy(deployer.address, guardians);
    await policyRegistry.waitForDeployment();
    addresses.policyRegistry = await policyRegistry.getAddress();
    console.log("✓ PolicyRegistry deployed to:", addresses.policyRegistry);
    console.log("  Guardians:", guardians);

    // Deploy SentinelAudit
    console.log("\n📝 Deploying SentinelAudit...");
    const SentinelAudit = await ethers.getContractFactory("SentinelAudit");
    const sentinelAudit = await SentinelAudit.deploy(deployer.address);
    await sentinelAudit.waitForDeployment();
    addresses.sentinelAudit = await sentinelAudit.getAddress();
    console.log("✓ SentinelAudit deployed to:", addresses.sentinelAudit);

    // Save deployment addresses
    const deploymentFile = path.join(
      __dirname,
      `../deployments/${network}-${Date.now()}.json`
    );
    fs.writeFileSync(deploymentFile, JSON.stringify(addresses, null, 2));
    console.log("\n✓ Deployment addresses saved to:", deploymentFile);

    // Also update the latest deployment file
    const latestFile = path.join(__dirname, "../deployments/latest.json");
    fs.writeFileSync(latestFile, JSON.stringify(addresses, null, 2));
    console.log("✓ Updated latest deployment file:", latestFile);

    // Save to .env for easy reference
    const envContent = `
# Contract Addresses on ${network}
MERKLE_ANCHOR_CONTRACT=${addresses.merkleAnchor}
POLICY_REGISTRY_CONTRACT=${addresses.policyRegistry}
SENTINEL_AUDIT_CONTRACT=${addresses.sentinelAudit}
`;
    const envFile = path.join(__dirname, "../.env.deployed");
    fs.writeFileSync(envFile, envContent);
    console.log("✓ Contract addresses saved to .env.deployed");

    // Save build artifacts
    await saveBuildArtifacts();

    console.log("\n✅ All contracts deployed successfully!");
    console.log("\nNext steps:");
    console.log("1. Update your .env file with the contract addresses");
    console.log("2. Authorize gateway addresses via setGatewayAuthorisation() methods");
    console.log("3. Configure guardians for PolicyRegistry if needed");

    return addresses;
  } catch (error) {
    console.error("❌ Deployment failed:", error);
    throw error;
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
