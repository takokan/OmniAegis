// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {MerkleProof} from "@openzeppelin/contracts/utils/cryptography/MerkleProof.sol";

/**
 * @title MerkleAnchor
 * @notice Anchors batches of off-chain decision proofs using Merkle roots for gas-efficient audit trails.
 * @dev
 * - Routine decisions are aggregated off-chain into batches.
 * - Only the root + compact metadata are persisted on-chain.
 * - Inclusion can be verified via `verifyDecisionInBatch` with Merkle proofs.
 */
contract MerkleAnchor is Ownable2Step, ReentrancyGuard {
    /// @notice Batch metadata stored per anchor id.
    /// @dev Field ordering is chosen for tighter storage packing.
    struct BatchAnchor {
        bytes32 merkleRoot; // root of decision leaf set
        bytes32 manifestCidHash; // keccak256(bytes(manifestCid))
        address gateway; // submitting gateway
        uint64 anchoredAt; // block timestamp
        uint64 startDecisionIndex; // starting sequence/index for off-chain batch window
        uint32 leafCount; // number of leaves committed in this root
    }

    /// @notice Emitted when a gateway allowlist state changes.
    event GatewayAuthorisationUpdated(address indexed gateway, bool authorised);

    /// @notice Emitted when a new batch root is anchored.
    /// @param batchId Monotonic batch id.
    /// @param merkleRoot Anchored Merkle root.
    /// @param startDecisionIndex Starting sequence/index in off-chain stream.
    /// @param leafCount Number of leaves represented by this root.
    /// @param manifestCidHash Hash of manifest CID.
    /// @param manifestCid Raw CID of batch manifest/proof bundle.
    /// @param gateway Submitting gateway.
    /// @param anchoredAt Timestamp at which root was anchored.
    event BatchAnchored(
        uint64 indexed batchId,
        bytes32 indexed merkleRoot,
        uint64 startDecisionIndex,
        uint32 leafCount,
        bytes32 manifestCidHash,
        string manifestCid,
        address indexed gateway,
        uint64 anchoredAt
    );

    /// @notice Reverts when caller is not an authorised gateway.
    error NotAuthorisedGateway(address caller);

    /// @notice Reverts when gateway address is zero.
    error ZeroAddressGateway();

    /// @notice Reverts for empty manifest CID.
    error EmptyManifestCid();

    /// @notice Reverts for zero Merkle root.
    error InvalidMerkleRoot();

    /// @notice Reverts when root was already anchored previously.
    error RootAlreadyAnchored(bytes32 merkleRoot);

    /// @notice Reverts when leaf count is zero.
    error InvalidLeafCount();

    /// @notice Reverts when batch id is out of range.
    error BatchNotFound(uint64 batchId);

    /// @notice Gateway allowlist for anchoring rights.
    mapping(address => bool) public isAuthorisedGateway;

    /// @notice Batch anchors keyed by batch id.
    mapping(uint64 => BatchAnchor) public batches;

    /// @notice True if a Merkle root has already been anchored.
    mapping(bytes32 => bool) public rootAnchored;

    /// @notice Monotonic identifier for the next batch.
    uint64 public nextBatchId;

    /**
     * @notice Initializes contract ownership.
     * @param initialOwner Owner address controlling gateway allowlist.
     */
    constructor(address initialOwner) Ownable(initialOwner) {
        if (initialOwner == address(0)) revert ZeroAddressGateway();
        nextBatchId = 1;
    }

    /**
     * @notice Restricts access to allowlisted gateway writers.
     */
    modifier onlyAuthorisedGateway() {
        if (!isAuthorisedGateway[msg.sender]) revert NotAuthorisedGateway(msg.sender);
        _;
    }

    /**
     * @notice Updates allowlist status for a gateway.
     * @param gateway Gateway address to update.
     * @param authorised New allowlist status.
     */
    function setGatewayAuthorisation(address gateway, bool authorised) external onlyOwner {
        if (gateway == address(0)) revert ZeroAddressGateway();
        isAuthorisedGateway[gateway] = authorised;
        emit GatewayAuthorisationUpdated(gateway, authorised);
    }

    /**
     * @notice Anchors a Merkle root that commits to a batch of off-chain decision proofs.
     * @dev
     * - Protected by `onlyAuthorisedGateway` and `nonReentrant`.
     * - Uses root deduplication to prevent accidental duplicate anchors.
     * - Stores only compact metadata and CID hash for gas-efficient persistence.
     *
     * @param merkleRoot Merkle root of all leaf hashes in the batch.
     * @param startDecisionIndex Starting decision index/offset represented by this batch.
     * @param leafCount Number of leaves committed under `merkleRoot`.
     * @param manifestCid IPFS CID of the batch manifest (contains per-leaf details).
     * @return batchId Newly allocated batch identifier.
     */
    function anchorBatch(
        bytes32 merkleRoot,
        uint64 startDecisionIndex,
        uint32 leafCount,
        string calldata manifestCid
    ) external onlyAuthorisedGateway nonReentrant returns (uint64 batchId) {
        batchId = _storeAnchor(merkleRoot, startDecisionIndex, leafCount, manifestCid);
    }

    /**
     * @notice Anchors a Merkle root under the canonical `anchorRoot` name expected by backend coordinators.
     * @dev Alias for `anchorBatch` retained for integration compatibility.
     * @param merkleRoot Merkle root of all leaf hashes in the batch.
     * @param startDecisionIndex Starting decision index/offset represented by this batch.
     * @param leafCount Number of leaves committed under `merkleRoot`.
     * @param manifestCid IPFS CID of the batch manifest (contains per-leaf details).
     * @return batchId Newly allocated batch identifier.
     */
    function anchorRoot(
        bytes32 merkleRoot,
        uint64 startDecisionIndex,
        uint32 leafCount,
        string calldata manifestCid
    ) external onlyAuthorisedGateway nonReentrant returns (uint64 batchId) {
        batchId = _storeAnchor(merkleRoot, startDecisionIndex, leafCount, manifestCid);
    }

    /**
     * @notice Stores a batch anchor after validating inputs.
     * @param merkleRoot Merkle root of all leaf hashes in the batch.
     * @param startDecisionIndex Starting decision index/offset represented by this batch.
     * @param leafCount Number of leaves committed under `merkleRoot`.
     * @param manifestCid IPFS CID of the batch manifest.
     * @return batchId Newly allocated batch identifier.
     */
    function _storeAnchor(
        bytes32 merkleRoot,
        uint64 startDecisionIndex,
        uint32 leafCount,
        string calldata manifestCid
    ) internal returns (uint64 batchId) {
        if (merkleRoot == bytes32(0)) revert InvalidMerkleRoot();
        if (leafCount == 0) revert InvalidLeafCount();
        if (bytes(manifestCid).length == 0) revert EmptyManifestCid();
        if (rootAnchored[merkleRoot]) revert RootAlreadyAnchored(merkleRoot);

        bytes32 cidHash = keccak256(bytes(manifestCid));
        uint64 ts = uint64(block.timestamp);

        batchId = nextBatchId;
        unchecked {
            nextBatchId = batchId + 1;
        }

        batches[batchId] = BatchAnchor({
            merkleRoot: merkleRoot,
            manifestCidHash: cidHash,
            gateway: msg.sender,
            anchoredAt: ts,
            startDecisionIndex: startDecisionIndex,
            leafCount: leafCount
        });
        rootAnchored[merkleRoot] = true;

        emit BatchAnchored(batchId, merkleRoot, startDecisionIndex, leafCount, cidHash, manifestCid, msg.sender, ts);
    }

    /**
     * @notice Verifies whether a leaf belongs to an anchored batch root.
     * @param batchId Existing batch id.
     * @param leafHash Leaf hash being proven.
     * @param proof Merkle sibling hashes from leaf to root.
     * @return valid True when proof reconstructs anchored root.
     */
    function verifyDecisionInBatch(
        uint64 batchId,
        bytes32 leafHash,
        bytes32[] calldata proof
    ) external view returns (bool valid) {
        BatchAnchor memory anchor = batches[batchId];
        if (anchor.merkleRoot == bytes32(0)) revert BatchNotFound(batchId);

        valid = MerkleProof.verifyCalldata(proof, anchor.merkleRoot, leafHash);
    }

    /**
     * @notice Retrieves batch anchor metadata by batch id.
     * @param batchId Batch identifier.
     * @return Batch metadata structure.
     */
    function getBatch(uint64 batchId) external view returns (BatchAnchor memory) {
        if (batches[batchId].merkleRoot == bytes32(0)) revert BatchNotFound(batchId);
        return batches[batchId];
    }

    /**
     * @notice Returns the next batch id that will be allocated.
     * @return The monotonic next batch identifier.
     */
    function getNextBatchId() external view returns (uint64) {
        return nextBatchId;
    }

    /**
     * @notice Checks if a Merkle root has been previously anchored.
     * @param merkleRoot The root to check.
     * @return True if the root is anchored.
     */
    function isRootAnchored(bytes32 merkleRoot) external view returns (bool) {
        return rootAnchored[merkleRoot];
    }
}
