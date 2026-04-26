import { expect } from "chai";
import { ethers } from "hardhat";
import { SentinelAudit } from "../typechain-types";
import { SignerWithAddress } from "@nomicfoundation/hardhat-ethers/signers";

describe("SentinelAudit", function () {
  let sentinelAudit: SentinelAudit;
  let owner: SignerWithAddress;
  let gateway: SignerWithAddress;
  let other: SignerWithAddress;

  beforeEach(async function () {
    [owner, gateway, other] = await ethers.getSigners();

    const SentinelAudit = await ethers.getContractFactory("SentinelAudit");
    sentinelAudit = await SentinelAudit.deploy(owner.address);
    await sentinelAudit.waitForDeployment();

    // Authorize gateway
    await sentinelAudit.setGatewayAuthorisation(gateway.address, true);
  });

  describe("Deployment", function () {
    it("Should set the right owner", async function () {
      expect(await sentinelAudit.owner()).to.equal(owner.address);
    });
  });

  describe("Gateway Authorization", function () {
    it("Should authorize a gateway", async function () {
      expect(await sentinelAudit.isAuthorisedGateway(gateway.address)).to.be.true;
    });

    it("Should revoke gateway authorization", async function () {
      await sentinelAudit.setGatewayAuthorisation(gateway.address, false);
      expect(await sentinelAudit.isAuthorisedGateway(gateway.address)).to.be.false;
    });

    it("Should reject zero address gateway", async function () {
      await expect(
        sentinelAudit.setGatewayAuthorisation(ethers.ZeroAddress, true)
      ).to.be.revertedWithCustomError(sentinelAudit, "ZeroAddressGateway");
    });
  });

  describe("Decision Recording", function () {
    const decisionId = ethers.id("test-decision-1");
    const policyId = BigInt(1);
    const riskScore = 5000;
    const action = 1;
    const highStakes = true;
    const evidenceCid = "QmTestCIDForDecision1234567890";

    it("Should record a decision", async function () {
      await expect(
        sentinelAudit
          .connect(gateway)
          .recordDecision(decisionId, policyId, riskScore, action, highStakes, evidenceCid)
      )
        .to.emit(sentinelAudit, "DecisionRecorded")
        .withArgs(
          decisionId,
          gateway.address,
          policyId,
          riskScore,
          action,
          highStakes,
          _,
          evidenceCid,
          _
        );

      expect(await sentinelAudit.hasDecision(decisionId)).to.be.true;
    });

    it("Should reject duplicate decisions", async function () {
      await sentinelAudit
        .connect(gateway)
        .recordDecision(decisionId, policyId, riskScore, action, highStakes, evidenceCid);

      await expect(
        sentinelAudit
          .connect(gateway)
          .recordDecision(decisionId, policyId, riskScore, action, highStakes, evidenceCid)
      ).to.be.revertedWithCustomError(sentinelAudit, "DecisionAlreadyRecorded");
    });

    it("Should reject unauthorized callers", async function () {
      await expect(
        sentinelAudit
          .connect(other)
          .recordDecision(decisionId, policyId, riskScore, action, highStakes, evidenceCid)
      ).to.be.revertedWithCustomError(sentinelAudit, "NotAuthorisedGateway");
    });

    it("Should validate inputs", async function () {
      // Invalid decision ID
      await expect(
        sentinelAudit
          .connect(gateway)
          .recordDecision(ethers.ZeroHash, policyId, riskScore, action, highStakes, evidenceCid)
      ).to.be.revertedWithCustomError(sentinelAudit, "InvalidDecisionId");

      // Invalid CID
      await expect(
        sentinelAudit
          .connect(gateway)
          .recordDecision(decisionId, policyId, riskScore, action, highStakes, "")
      ).to.be.revertedWithCustomError(sentinelAudit, "EmptyEvidenceCid");
    });
  });

  describe("Decision Retrieval", function () {
    it("Should retrieve decision by ID", async function () {
      const decisionId = ethers.id("test-decision-2");
      const policyId = BigInt(2);
      const riskScore = 7500;
      const action = 2;
      const evidenceCid = "QmTestCID2";

      await sentinelAudit
        .connect(gateway)
        .recordDecision(decisionId, policyId, riskScore, action, false, evidenceCid);

      const decision = await sentinelAudit.getDecision(decisionId);
      expect(decision.policyId).to.equal(policyId);
      expect(decision.riskScoreBps).to.equal(riskScore);
      expect(decision.action).to.equal(action);
      expect(decision.gateway).to.equal(gateway.address);
    });
  });

  describe("Batch Recording", function () {
    it("Should record multiple decisions in one batch", async function () {
      const decisions = [ethers.id("batch-1"), ethers.id("batch-2"), ethers.id("batch-3")];
      const policyIds = [BigInt(1), BigInt(2), BigInt(3)];
      const riskScores = [5000, 6000, 7000];
      const actions = [1, 2, 3];
      const highStakes = [true, false, true];
      const cids = ["QmCID1", "QmCID2", "QmCID3"];

      await expect(
        sentinelAudit
          .connect(gateway)
          .recordDecisionBatch(decisions, policyIds, riskScores, actions, highStakes, cids)
      ).to.emit(sentinelAudit, "DecisionRecorded");

      for (const decisionId of decisions) {
        expect(await sentinelAudit.hasDecision(decisionId)).to.be.true;
      }
    });

    it("Should validate batch array lengths", async function () {
      const decisions = [ethers.id("batch-1")];
      const policyIds = [BigInt(1), BigInt(2)]; // Mismatched length

      await expect(
        sentinelAudit
          .connect(gateway)
          .recordDecisionBatch(decisions, policyIds, [5000], [1], [true], ["QmCID1"])
      ).to.be.revertedWithCustomError(sentinelAudit, "InvalidDecisionId");
    });
  });
});
