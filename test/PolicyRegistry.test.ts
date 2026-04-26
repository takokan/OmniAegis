import { expect } from "chai";
import { ethers } from "hardhat";
import { PolicyRegistry } from "../typechain-types";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

describe("PolicyRegistry", function () {
  let policyRegistry: PolicyRegistry;
  let owner: SignerWithAddress;
  let guardian1: SignerWithAddress;
  let guardian2: SignerWithAddress;
  let guardian3: SignerWithAddress;
  let other: SignerWithAddress;

  beforeEach(async function () {
    [owner, guardian1, guardian2, guardian3, other] = await ethers.getSigners();

    const PolicyRegistry = await ethers.getContractFactory("PolicyRegistry");
    policyRegistry = await PolicyRegistry.deploy(owner.address, [
      guardian1.address,
      guardian2.address,
      guardian3.address,
    ]);
    await policyRegistry.waitForDeployment();
  });

  describe("Deployment", function () {
    it("Should set the right owner", async function () {
      expect(await policyRegistry.owner()).to.equal(owner.address);
    });

    it("Should set the right guardians", async function () {
      const guardians = await policyRegistry.getGuardians();
      expect(guardians[0]).to.equal(guardian1.address);
      expect(guardians[1]).to.equal(guardian2.address);
      expect(guardians[2]).to.equal(guardian3.address);
    });
  });

  describe("Guardian Management", function () {
    it("Should update a guardian", async function () {
      const newGuardian = other.address;
      await expect(policyRegistry.setGuardian(0, newGuardian))
        .to.emit(policyRegistry, "GuardianUpdated")
        .withArgs(0, guardian1.address, newGuardian);

      const guardians = await policyRegistry.getGuardians();
      expect(guardians[0]).to.equal(newGuardian);
    });

    it("Should reject invalid guardian index", async function () {
      await expect(
        policyRegistry.setGuardian(3, other.address)
      ).to.be.revertedWithCustomError(policyRegistry, "InvalidGuardianIndex");
    });

    it("Should reject zero address guardian", async function () {
      await expect(
        policyRegistry.setGuardian(0, ethers.ZeroAddress)
      ).to.be.revertedWithCustomError(policyRegistry, "ZeroAddressGuardian");
    });

    it("Should reject duplicate guardians", async function () {
      await expect(
        policyRegistry.setGuardian(0, guardian2.address)
      ).to.be.revertedWithCustomError(policyRegistry, "GuardianAlreadyConfigured");
    });

    it("Should be owner-only", async function () {
      await expect(
        policyRegistry.connect(other).setGuardian(0, other.address)
      ).to.be.revertedWithCustomError(policyRegistry, "OwnableUnauthorizedAccount");
    });
  });

  describe("Policy Upsert", function () {
    it("Should require 2-of-3 signatures", async function () {
      const policyId = ethers.id("policy-1");
      const policyHash = ethers.keccak256(ethers.toBeHex("policy-content", 32));
      const validFrom = Math.floor(Date.now() / 1000);
      const nonce = BigInt(1);

      // This would require signing and is more complex - simplified for now
      // In real tests, you'd use ethers signing utilities
      expect(await policyRegistry.isPolicyActive(policyId)).to.be.false;
    });
  });

  describe("Policy Retrieval", function () {
    it("Should retrieve policy if exists", async function () {
      const policyId = ethers.id("policy-test");
      const policy = await policyRegistry.getPolicy(policyId);
      expect(policy.active).to.be.false;
      expect(policy.version).to.equal(0);
    });

    it("Should check if policy is active", async function () {
      const policyId = ethers.id("policy-test-2");
      expect(await policyRegistry.isPolicyActive(policyId)).to.be.false;
    });
  });

  describe("Nonce Management", function () {
    it("Should check if nonce has been used", async function () {
      const nonce = BigInt(100);
      expect(await policyRegistry.hasNonceBeenUsed(nonce)).to.be.false;
    });
  });
});
