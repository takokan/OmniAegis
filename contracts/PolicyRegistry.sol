// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title PolicyRegistry
 * @notice Maintains governance-approved policy snapshots using 2-of-3 signer approval.
 * @dev
 * - Signature verification is implemented with `ecrecover` as requested.
 * - Signatures are tied to `(chainId, contract, payload)` for replay resistance.
 * - `nonce` is single-use globally to prevent transaction replay.
 */
contract PolicyRegistry is Ownable2Step, ReentrancyGuard {
    /// @notice Policy metadata optimized for compact storage.
    struct Policy {
        bytes32 policyHash; // hash of canonical policy artifact
        uint64 validFrom; // unix time from which policy applies
        uint64 updatedAt; // unix time at which policy was last updated
        uint32 version; // monotonic version per policy id
        bool active; // registry status flag
    }

    /// @notice Type hash for policy upsert payloads.
    bytes32 public constant UPSERT_TYPEHASH =
        keccak256("UpsertPolicy(bytes32 policyId,bytes32 policyHash,uint64 validFrom,uint64 nonce)");

    /// @notice Type hash for policy revocation payloads.
    bytes32 public constant REVOKE_TYPEHASH = keccak256("RevokePolicy(bytes32 policyId,uint64 nonce)");

    /// @notice Emitted after a policy is inserted or updated.
    event PolicyUpserted(
        bytes32 indexed policyId,
        bytes32 indexed policyHash,
        uint32 version,
        uint64 validFrom,
        uint64 updatedAt,
        address indexed executor
    );

    /// @notice Emitted after a policy is revoked.
    event PolicyRevoked(bytes32 indexed policyId, uint32 version, uint64 updatedAt, address indexed executor);

    /// @notice Emitted when a guardian is updated.
    event GuardianUpdated(uint8 indexed index, address indexed oldGuardian, address indexed newGuardian);

    /// @notice Reverts when signature count is insufficient for threshold.
    error InsufficientSignatures(uint256 provided, uint256 required);

    /// @notice Reverts on malformed signature bytes.
    error InvalidSignatureLength(uint256 length);

    /// @notice Reverts when recovered signer is not one of the 3 guardians.
    error UnauthorizedSigner(address signer);

    /// @notice Reverts when the same signer appears more than once.
    error DuplicateSigner(address signer);

    /// @notice Reverts when `ecrecover` fails to recover a signer.
    error InvalidSignature();

    /// @notice Reverts when a nonce has already been consumed.
    error NonceAlreadyUsed(uint64 nonce);

    /// @notice Reverts when guardian address is zero.
    error ZeroAddressGuardian();

    /// @notice Reverts when guardian index is outside [0, 2].
    error InvalidGuardianIndex(uint8 index);

    /// @notice Reverts when guardian is duplicated in the configured set.
    error GuardianAlreadyConfigured(address guardian);

    /// @notice Reverts when policy id is zero.
    error InvalidPolicyId();

    /// @notice The number of required signatures for governance actions.
    uint256 public constant REQUIRED_SIGNATURES = 2;

    /// @dev secp256k1n/2 used to enforce canonical low-s signatures.
    uint256 private constant SECP256K1N_DIV_2 =
        0x7FFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF5D576E7357A4501DDFE92F46681B20A0;

    /// @notice 3 governance signers participating in the 2-of-3 multisig process.
    address[3] public guardians;

    /// @notice Policy data keyed by policy id.
    mapping(bytes32 => Policy) public policies;

    /// @notice Replay-protection bitmap keyed by nonce.
    mapping(uint64 => bool) public usedNonces;

    /**
     * @notice Initializes contract owner and guardian set.
     * @param initialOwner Address for ownership control.
     * @param initialGuardians Fixed-size array of three guardian addresses.
     */
    constructor(address initialOwner, address[3] memory initialGuardians) Ownable(initialOwner) {
        if (initialOwner == address(0)) revert ZeroAddressGuardian();

        for (uint8 i = 0; i < 3; ) {
            address g = initialGuardians[i];
            if (g == address(0)) revert ZeroAddressGuardian();
            for (uint8 j = 0; j < i; ) {
                if (initialGuardians[j] == g) revert GuardianAlreadyConfigured(g);
                unchecked {
                    ++j;
                }
            }
            guardians[i] = g;
            unchecked {
                ++i;
            }
        }
    }

    /**
     * @notice Updates a guardian slot.
     * @dev Owner-only break-glass administration for signer rotation.
     * @param index Guardian array index in [0, 2].
     * @param newGuardian New guardian address.
     */
    function setGuardian(uint8 index, address newGuardian) external onlyOwner {
        if (index > 2) revert InvalidGuardianIndex(index);
        if (newGuardian == address(0)) revert ZeroAddressGuardian();
        for (uint8 i = 0; i < 3; ) {
            if (i != index && guardians[i] == newGuardian) revert GuardianAlreadyConfigured(newGuardian);
            unchecked {
                ++i;
            }
        }

        address oldGuardian = guardians[index];
        guardians[index] = newGuardian;
        emit GuardianUpdated(index, oldGuardian, newGuardian);
    }

    /**
     * @notice Inserts or updates a policy using 2-of-3 guardian signatures.
     * @dev
     * - Any executor can submit; authorization is determined by signatures.
     * - Uses single-use nonce to block replay.
     * - Protected with `nonReentrant` to harden execution flow.
     *
     * @param policyId Unique policy identifier.
     * @param policyHash Canonical policy hash (e.g., IPFS file digest or JSON digest).
     * @param validFrom Policy activation timestamp.
     * @param nonce Unique one-time nonce signed by guardians.
     * @param signatures Array of guardian signatures over typed payload.
     */
    function upsertPolicy(
        bytes32 policyId,
        bytes32 policyHash,
        uint64 validFrom,
        uint64 nonce,
        bytes[] calldata signatures
    ) external nonReentrant {
        if (policyId == bytes32(0)) revert InvalidPolicyId();
        _consumeNonce(nonce);

        bytes32 digest = _toEthSignedMessageHash(
            keccak256(abi.encode(UPSERT_TYPEHASH, block.chainid, address(this), policyId, policyHash, validFrom, nonce))
        );

        _requireThresholdSignatures(digest, signatures);

        Policy storage p = policies[policyId];
        p.policyHash = policyHash;
        p.validFrom = validFrom;
        p.updatedAt = uint64(block.timestamp);
        p.version += 1;
        p.active = true;

        emit PolicyUpserted(policyId, policyHash, p.version, validFrom, p.updatedAt, msg.sender);
    }

    /**
     * @notice Revokes an existing policy using 2-of-3 guardian signatures.
     * @param policyId Policy identifier to revoke.
     * @param nonce Unique one-time nonce signed by guardians.
     * @param signatures Array of guardian signatures over revocation payload.
     */
    function revokePolicy(bytes32 policyId, uint64 nonce, bytes[] calldata signatures) external nonReentrant {
        if (policyId == bytes32(0)) revert InvalidPolicyId();
        _consumeNonce(nonce);

        bytes32 digest = _toEthSignedMessageHash(
            keccak256(abi.encode(REVOKE_TYPEHASH, block.chainid, address(this), policyId, nonce))
        );

        _requireThresholdSignatures(digest, signatures);

        Policy storage p = policies[policyId];
        p.active = false;
        p.updatedAt = uint64(block.timestamp);
        p.version += 1;

        emit PolicyRevoked(policyId, p.version, p.updatedAt, msg.sender);
    }

    /**
     * @notice Validates that at least 2 unique guardians signed the digest.
     * @param digest Signed payload digest.
     * @param signatures Candidate signatures.
     */
    function _requireThresholdSignatures(bytes32 digest, bytes[] calldata signatures) internal view {
        if (signatures.length < REQUIRED_SIGNATURES) {
            revert InsufficientSignatures(signatures.length, REQUIRED_SIGNATURES);
        }

        address[3] memory seen;
        uint256 approvals;

        for (uint256 i = 0; i < signatures.length; ) {
            address signer = _recoverSigner(digest, signatures[i]);
            if (!_isGuardian(signer)) revert UnauthorizedSigner(signer);

            for (uint256 j = 0; j < approvals; ) {
                if (seen[j] == signer) revert DuplicateSigner(signer);
                unchecked {
                    ++j;
                }
            }

            if (approvals < 3) {
                seen[approvals] = signer;
            }
            approvals += 1;

            if (approvals >= REQUIRED_SIGNATURES) {
                return;
            }

            unchecked {
                ++i;
            }
        }

        revert InsufficientSignatures(approvals, REQUIRED_SIGNATURES);
    }

    /**
     * @notice Marks a nonce as used and reverts on reuse.
     * @param nonce Nonce value to consume.
     */
    function _consumeNonce(uint64 nonce) internal {
        if (usedNonces[nonce]) revert NonceAlreadyUsed(nonce);
        usedNonces[nonce] = true;
    }

    /**
     * @notice Recovers signer address from a 65-byte ECDSA signature via `ecrecover`.
     * @param digest Message digest that was signed.
     * @param signature Signature bytes in `{r}{s}{v}` format.
     * @return signer Recovered signer address.
     */
    function _recoverSigner(bytes32 digest, bytes calldata signature) internal pure returns (address signer) {
        if (signature.length != 65) revert InvalidSignatureLength(signature.length);

        bytes32 r;
        bytes32 s;
        uint8 v;

        assembly {
            r := calldataload(signature.offset)
            s := calldataload(add(signature.offset, 32))
            v := byte(0, calldataload(add(signature.offset, 64)))
        }

        if (v < 27) v += 27;
        if (v != 27 && v != 28) revert InvalidSignature();
        if (uint256(s) > SECP256K1N_DIV_2) revert InvalidSignature();

        signer = ecrecover(digest, v, r, s);
        if (signer == address(0)) revert InvalidSignature();
    }

    /**
     * @notice Checks if an address is one of the configured guardians.
     * @param signer Address to validate.
     * @return True when `signer` is a guardian.
     */
    function _isGuardian(address signer) internal view returns (bool) {
        return signer == guardians[0] || signer == guardians[1] || signer == guardians[2];
    }

    /**
     * @notice Builds an Ethereum Signed Message hash from a raw digest.
     * @param digest Raw payload digest.
     * @return prefixedDigest EIP-191 prefixed digest.
     */
    function _toEthSignedMessageHash(bytes32 digest) internal pure returns (bytes32 prefixedDigest) {
        prefixedDigest = keccak256(abi.encodePacked("\x19Ethereum Signed Message:\n32", digest));
    }

    /**
     * @notice Retrieves a policy snapshot by id.
     * @param policyId Unique policy identifier.
     * @return policy The stored policy record.
     */
    function getPolicy(bytes32 policyId) external view returns (Policy memory policy) {
        return policies[policyId];
    }

    /**
     * @notice Checks if a policy is currently active.
     * @param policyId Policy identifier.
     * @return True if policy exists and is active.
     */
    function isPolicyActive(bytes32 policyId) external view returns (bool) {
        return policies[policyId].active;
    }

    /**
     * @notice Returns all three guardian addresses.
     * @return Array of three guardian addresses.
     */
    function getGuardians() external view returns (address[3] memory) {
        return guardians;
    }

    /**
     * @notice Checks if a nonce has been consumed.
     * @param nonce Nonce value to check.
     * @return True if nonce has been used.
     */
    function hasNonceBeenUsed(uint64 nonce) external view returns (bool) {
        return usedNonces[nonce];
    }
