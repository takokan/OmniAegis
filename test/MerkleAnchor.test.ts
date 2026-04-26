import { expect } from "chai";
import { ethers } from "hardhat";
import { MerkleAnchor, SentinelAudit, PolicyRegistry } from "../typechain-types";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

describe("MerkleAnchor", function () {
  let merkleAnchor: MerkleAnchor;
  let owner: SignerWithAddress;
  let gateway: SignerWithAddress;
  let other: SignerWithAddress;

  beforeEach(async function () {
    [owner, gateway, other] = await ethers.getSigners();

    const MerkleAnchor = await ethers.getContractFactory("MerkleAnchor");
    merkleAnchor = await MerkleAnchor.deploy(owner.address);
    await merkleAnchor.waitForDeployment();

    // Authorize gateway
    await merkleAnchor.setGatewayAuthorisation(gateway.address, true);
  });

  describe("Deployment", function () {
    it("Should set the right owner", async function () {
      expect(await merkleAnchor.owner()).to.equal(owner.address);
    });

    it("Should initialize nextBatchId to 1", async function () {
      expect(await merkleAnchor.getNextBatchId()).to.equal(1);
    });
  });

  describe("Gateway Authorization", function () {
    it("Should authorize a gateway", async function () {
      expect(await merkleAnchor.isAuthorisedGateway(gateway.address)).to.be.true;
    });

    it("Should revoke gateway authorization", async function () {
      await merkleAnchor.setGatewayAuthorisation(gateway.address, false);
      expect(await merkleAnchor.isAuthorisedGateway(gateway.address)).to.be.false;
    });

    it("Should reject zero address gateway", async function () {
      await expect(
        merkleAnchor.setGatewayAuthorisation(ethers.ZeroAddress, true)
      ).to.be.revertedWithCustomError(merkleAnchor, "ZeroAddressGateway");
    });

    it("Should be owner-only", async function () {
      await expect(
        merkleAnchor.connect(other).setGatewayAuthorisation(other.address, true)
      ).to.be.revertedWithCustomError(merkleAnchor, "OwnableUnauthorizedAccount");
    });
  });

  describe("Batch Anchoring", function () {
    const merkleRoot = ethers.keccak256(ethers.toBeHex("test-root", 32));
    const startIndex = BigInt(0);
    const leafCount = BigInt(100);
    const manifestCid = "QmTestCID1234567890abcdef";

    it("Should anchor a batch", async function () {
      await expect(
        merkleAnchor
          .connect(gateway)
          .anchorBatch(merkleRoot, startIndex, leafCount, manifestCid)
      )
        .to.emit(merkleAnchor, "BatchAnchored")
        .withArgs(1, merkleRoot, startIndex, leafCount, _, manifestCid, gateway.address, _);

      expect(await merkleAnchor.isRootAnchored(merkleRoot)).to.be.true;
    });

    it("Should assign monotonic batch IDs", async function () {
      const root1 = ethers.keccak256(ethers.toBeHex("root1", 32));
      const root2 = ethers.keccak256(ethers.toBeHex("root2", 32));

      const tx1 = await merkleAnchor
        .connect(gateway)
        .anchorBatch(root1, 0, 10, "QmCID1");
      await tx1.wait();

      const tx2 = await merkleAnchor
        .connect(gateway)
        .anchorBatch(root2, 10, 20, "QmCID2");
      await tx2.wait();

      expect(await merkleAnchor.getNextBatchId()).to.equal(3);
    });

    it("Should reject duplicate roots", async function () {
      await merkleAnchor
        .connect(gateway)
        .anchorBatch(merkleRoot, 0, 10, "QmCID1");

      await expect(
        merkleAnchor
          .connect(gateway)
          .anchorBatch(merkleRoot, 10, 20, "QmCID2")
      ).to.be.revertedWithCustomError(merkleAnchor, "RootAlreadyAnchored");
    });

    it("Should reject unauthorized callers", async function () {
      await expect(
        merkleAnchor.connect(other).anchorBatch(merkleRoot, 0, 10, manifestCid)
      ).to.be.revertedWithCustomError(merkleAnchor, "NotAuthorisedGateway");
    });

    it("Should validate inputs", async function () {
      // Invalid root
      await expect(
        merkleAnchor
          .connect(gateway)
          .anchorBatch(ethers.ZeroHash, 0, 10, manifestCid)
      ).to.be.revertedWithCustomError(merkleAnchor, "InvalidMerkleRoot");

      // Invalid leaf count
      await expect(
        merkleAnchor.connect(gateway).anchorBatch(merkleRoot, 0, 0, manifestCid)
      ).to.be.revertedWithCustomError(merkleAnchor, "InvalidLeafCount");

      // Invalid CID
      await expect(
        merkleAnchor.connect(gateway).anchorBatch(merkleRoot, 0, 10, "")
      ).to.be.revertedWithCustomError(merkleAnchor, "EmptyManifestCid");
    });
  });

  describe("Batch Retrieval", function () {
    it("Should retrieve batch by ID", async function () {
      const merkleRoot = ethers.keccak256(ethers.toBeHex("test-root", 32));
      const manifestCid = "QmTestCID";

      await merkleAnchor
        .connect(gateway)
        .anchorBatch(merkleRoot, 0, 100, manifestCid);

      const batch = await merkleAnchor.getBatch(1);
      expect(batch.merkleRoot).to.equal(merkleRoot);
      expect(batch.leafCount).to.equal(100);
      expect(batch.gateway).to.equal(gateway.address);
    });

    it("Should revert for non-existent batch", async function () {
      await expect(merkleAnchor.getBatch(999)).to.be.revertedWithCustomError(
        merkleAnchor,
        "BatchNotFound"
      );
    });
  });

  describe("Merkle Verification", function () {
    it("Should verify valid Merkle proofs", async function () {
      // Create a simple tree: leaf -> root
      const leaf = ethers.keccak256(ethers.toBeHex("leaf-data", 32));
      const root = leaf; // For this test, use the leaf as root

      await merkleAnchor
        .connect(gateway)
        .anchorBatch(root, 0, 1, "QmTestCID");

      // Verify with empty proof (leaf == root in this trivial case)
      const isValid = await merkleAnchor.verifyDecisionInBatch(1, leaf, []);
      expect(isValid).to.be.true;
    });
  });
});
