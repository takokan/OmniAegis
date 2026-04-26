// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title SentinelAudit
 * @notice Records high-stakes ML enforcement decisions with evidence references for verifiable auditability.
 * @dev
 * - Gateways are explicitly allowlisted via `authoriseGateway`.
 * - Every decision stores a deterministic hash of the IPFS CID to guarantee immutable linkage.
 * - Full CID is emitted in logs for off-chain indexers while using compact on-chain storage.
 */
contract SentinelAudit is Ownable2Step, ReentrancyGuard {
    /// @notice Represents one immutable audit decision record.
    /// @dev Fields are arranged to improve packing and reduce storage gas where possible.
    struct DecisionRecord {
        bytes32 evidenceCidHash; // keccak256(bytes(ipfsCid))
        address gateway; // authoring gateway address
        uint64 timestamp; // block timestamp at record time
        uint64 policyId; // policy snapshot identifier used by inference
        uint32 riskScoreBps; // risk in basis points [0, 10000]
        uint8 action; // encoded enforcement action
        bool highStakes; // true for high-stakes direct writes
    }

    /// @notice Emitted when a gateway address allowlist state changes.
    /// @param gateway The gateway address.
    /// @param authorised Whether the gateway is now authorised.
    event GatewayAuthorisationUpdated(address indexed gateway, bool authorised);

    /// @notice Emitted when a decision is written to the immutable audit ledger.
    /// @param decisionId Unique decision identifier.
    /// @param gateway Gateway that wrote the decision.
    /// @param policyId Policy identifier used to evaluate the decision.
    /// @param riskScoreBps Risk score in basis points.
    /// @param action Encoded enforcement action.
    /// @param highStakes Whether this is a high-stakes write.
    /// @param evidenceCidHash Hash of the IPFS CID.
    /// @param evidenceCid Raw IPFS CID for indexers and external verifiers.
    /// @param timestamp Block timestamp of recording.
    event DecisionRecorded(
        bytes32 indexed decisionId,
        address indexed gateway,
        uint64 indexed policyId,
        uint32 riskScoreBps,
        uint8 action,
        bool highStakes,
        bytes32 evidenceCidHash,
        string evidenceCid,
        uint64 timestamp
    );

    /// @notice Reverts when a caller is not an authorised gateway.
    error NotAuthorisedGateway(address caller);

    /// @notice Reverts when the supplied decision id is zero.
    error InvalidDecisionId();

    /// @notice Reverts when the supplied IPFS CID is empty.
    error EmptyEvidenceCid();

    /// @notice Reverts when a decision id has already been recorded.
    /// @param decisionId The duplicated decision identifier.
    error DecisionAlreadyRecorded(bytes32 decisionId);

    /// @notice Reverts when a gateway address is zero.
    error ZeroAddressGateway();

    /// @notice True if address is approved to write decision records.
    mapping(address => bool) public isAuthorisedGateway;

    /// @notice Decision records by unique decision id.
    mapping(bytes32 => DecisionRecord) private _decisionById;

    /// @notice Tracks existence to avoid sentinel-value ambiguity in structs.
    mapping(bytes32 => bool) public decisionExists;

    /**
     * @notice Creates the audit contract and sets initial owner.
     * @param initialOwner Address that controls gateway allowlisting.
     */
    constructor(address initialOwner) Ownable(initialOwner) {
        if (initialOwner == address(0)) revert ZeroAddressGateway();
    }

    /**
     * @notice Restricts a function to addresses allowlisted as gateways.
     */
    modifier onlyAuthorisedGateway() {
        if (!isAuthorisedGateway[msg.sender]) revert NotAuthorisedGateway(msg.sender);
        _;
    }

    /**
     * @notice Allowlists or removes a gateway writer.
     * @dev Owner-only administrative method.
     * @param gateway Gateway address to update.
     * @param authorised New authorisation state.
     */
    function setGatewayAuthorisation(address gateway, bool authorised) external onlyOwner {
        if (gateway == address(0)) revert ZeroAddressGateway();
        isAuthorisedGateway[gateway] = authorised;
        emit GatewayAuthorisationUpdated(gateway, authorised);
    }

    /**
     * @notice Records a single high-stakes decision with immutable evidence linkage.
     * @dev
     * - Protected by `onlyAuthorisedGateway` and `nonReentrant`.
     * - Stores only a CID hash to keep storage compact.
     * - Emits full CID in event for off-chain verification pipelines.
     *
     * @param decisionId Unique id for this decision.
     * @param policyId Policy identifier used by the gateway.
     * @param riskScoreBps Risk score in basis points.
     * @param action Encoded action taken by SentinelAgent.
     * @param highStakes Whether decision is high-stakes.
     * @param evidenceCid IPFS CID containing decision proof/evidence package.
     */
    function recordDecision(
        bytes32 decisionId,
        uint64 policyId,
        uint32 riskScoreBps,
        uint8 action,
        bool highStakes,
        string calldata evidenceCid
    ) external onlyAuthorisedGateway nonReentrant {
        if (decisionId == bytes32(0)) revert InvalidDecisionId();
        if (bytes(evidenceCid).length == 0) revert EmptyEvidenceCid();
        if (decisionExists[decisionId]) revert DecisionAlreadyRecorded(decisionId);

        bytes32 cidHash = keccak256(bytes(evidenceCid));
        uint64 ts = uint64(block.timestamp);

        _decisionById[decisionId] = DecisionRecord({
            evidenceCidHash: cidHash,
            gateway: msg.sender,
            timestamp: ts,
            policyId: policyId,
            riskScoreBps: riskScoreBps,
            action: action,
            highStakes: highStakes
        });
        decisionExists[decisionId] = true;

        emit DecisionRecorded(
            decisionId,
            msg.sender,
            policyId,
            riskScoreBps,
            action,
            highStakes,
            cidHash,
            evidenceCid,
            ts
        );
    }

    /**
     * @notice Reads an immutable decision record by id.
     * @param decisionId Unique decision identifier.
     * @return record The stored decision record.
     */
    function getDecision(bytes32 decisionId) external view returns (DecisionRecord memory record) {
        record = _decisionById[decisionId];
    }

    /**
     * @notice Checks if a decision has been recorded.
     * @param decisionId The decision identifier to check.
     * @return True if the decision exists.
     */
    function hasDecision(bytes32 decisionId) external view returns (bool) {
        return decisionExists[decisionId];
    }

    /**
     * @notice Batch records multiple high-stakes decisions in a single transaction.
     * @dev More gas-efficient than multiple individual recordDecision calls.
     * @param decisions Array of decision parameters (id, policyId, riskScore, action, highStakes, evidenceCid).
     */
    function recordDecisionBatch(
        bytes32[] calldata decisions,
        uint64[] calldata policyIds,
        uint32[] calldata riskScores,
        uint8[] calldata actions,
        bool[] calldata highStakesFlags,
        string[] calldata evidenceCids
    ) external onlyAuthorisedGateway nonReentrant {
        uint256 len = decisions.length;
        if (
            len == 0 ||
            len != policyIds.length ||
            len != riskScores.length ||
            len != actions.length ||
            len != highStakesFlags.length ||
            len != evidenceCids.length
        ) revert InvalidDecisionId();

        for (uint256 i = 0; i < len; ) {
            bytes32 decisionId = decisions[i];
            if (decisionId == bytes32(0)) revert InvalidDecisionId();
            if (bytes(evidenceCids[i]).length == 0) revert EmptyEvidenceCid();
            if (decisionExists[decisionId]) revert DecisionAlreadyRecorded(decisionId);

            bytes32 cidHash = keccak256(bytes(evidenceCids[i]));
            uint64 ts = uint64(block.timestamp);

            _decisionById[decisionId] = DecisionRecord({
                evidenceCidHash: cidHash,
                gateway: msg.sender,
                timestamp: ts,
                policyId: policyIds[i],
                riskScoreBps: riskScores[i],
                action: actions[i],
                highStakes: highStakesFlags[i]
            });
            decisionExists[decisionId] = true;

            emit DecisionRecorded(
                decisionId,
                msg.sender,
                policyIds[i],
                riskScores[i],
                actions[i],
                highStakesFlags[i],
                cidHash,
                evidenceCids[i],
                ts
            );

            unchecked {
                ++i;
            }
        }
    }
}
