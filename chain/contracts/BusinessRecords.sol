// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @notice Append-only organizational records. Wallet namespaces are NOT verified legal identities.
/// @dev Store salted commitments only. No file bodies, legal names, share registers or financial details go on-chain.
contract BusinessRecords {
    enum Kind { Equity, Agreement, Legal, Financial }
    struct Organization { address controller; address pendingController; bytes32 identityCommitment; uint64 policyVersion; uint8 quorum; }
    struct Grant { uint8 mask; uint64 expires; }
    struct Record {
        bytes32 commitment;
        bytes32 previous;
        bytes32 recordHash;
        address author;
        uint64 recordedAt;
        uint64 policyVersion;
        uint32 approvals;
        uint8 quorum;
        Kind kind;
        bool correction;
    }
    uint256 public nextOrganization = 1;
    mapping(uint256 => Organization) public organizations;
    mapping(uint256 => address[]) private policySigners;
    mapping(uint256 => mapping(address => Grant)) public grants;
    mapping(uint256 => mapping(bytes32 => uint256)) public latestVersion;
    mapping(uint256 => mapping(bytes32 => mapping(uint256 => Record))) public records;
    mapping(bytes32 => address[]) private recordSigners;
    mapping(bytes32 => mapping(address => bool)) public approvedBy;
    error Invalid(); error Unauthorized(); error StaleVersion();
    event OrganizationCreated(uint256 indexed organization, address indexed controller, bytes32 identityCommitment);
    event PolicyChanged(uint256 indexed organization, uint64 version, address[] signers, uint8 quorum);
    event ControllerProposed(uint256 indexed organization, address indexed pending);
    event ControllerChanged(uint256 indexed organization, address indexed previous, address indexed current);
    event GrantChanged(uint256 indexed organization, address indexed publisher, uint8 mask, uint64 expires);
    event Recorded(uint256 indexed organization, bytes32 indexed key, uint256 indexed version, bytes32 recordHash, bytes32 commitment, bytes32 previous, Kind kind, bool correction, address author);
    event Attested(bytes32 indexed recordHash, address indexed signer, bool approved, uint32 approvals);

    function createOrganization(bytes32 identityCommitment, address[] calldata signers, uint8 quorum) external returns (uint256 org) {
        if (identityCommitment == bytes32(0)) revert Invalid();
        org = nextOrganization++;
        organizations[org].controller = msg.sender;
        organizations[org].identityCommitment = identityCommitment;
        emit OrganizationCreated(org, msg.sender, identityCommitment);
        _setPolicy(org, signers, quorum);
    }
    function setPolicy(uint256 org, address[] calldata signers, uint8 quorum) external {
        _controller(org); _setPolicy(org, signers, quorum);
    }
    function _setPolicy(uint256 org, address[] calldata signers, uint8 quorum) private {
        if (quorum == 0 || signers.length > 32 || quorum > signers.length) revert Invalid();
        for (uint256 i; i < signers.length; ++i) {
            if (signers[i] == address(0)) revert Invalid();
            for (uint256 j; j < i; ++j) if (signers[i] == signers[j]) revert Invalid();
        }
        policySigners[org] = signers;
        Organization storage o = organizations[org]; ++o.policyVersion; o.quorum = quorum;
        emit PolicyChanged(org, o.policyVersion, signers, quorum);
    }
    function getPolicy(uint256 org) external view returns (address[] memory) { return policySigners[org]; }
    function getSigners(bytes32 recordHash) external view returns (address[] memory) { return recordSigners[recordHash]; }
    function proposeController(uint256 org, address next) external {
        _controller(org); // zero explicitly cancels a pending transfer; it does not renounce the controller.
        organizations[org].pendingController = next; emit ControllerProposed(org, next);
    }
    function acceptController(uint256 org) external {
        Organization storage o = organizations[org];
        if (msg.sender != o.pendingController) revert Unauthorized();
        address previous = o.controller; o.controller = msg.sender; o.pendingController = address(0);
        emit ControllerChanged(org, previous, msg.sender);
    }
    /// @notice Bitmask: equity=1, agreement=2, legal=4, financial=8. Publication never implies approval.
    function setGrant(uint256 org, address publisher, uint8 mask, uint64 expires) external {
        _controller(org);
        if (publisher == address(0) || mask > 15 || (mask != 0 && (expires <= block.timestamp || expires > block.timestamp + 90 days))) revert Invalid();
        grants[org][publisher] = Grant(mask, expires); emit GrantChanged(org, publisher, mask, expires);
    }
    function append(uint256 org, bytes32 key, uint256 expectedVersion, Kind kind, bytes32 commitment, bool correction) external returns (uint256 version) {
        Organization storage o = organizations[org]; Grant memory g = grants[org][msg.sender];
        if (o.controller == address(0) || (msg.sender != o.controller && (g.mask & (uint8(1) << uint8(kind)) == 0 || block.timestamp > g.expires))) revert Unauthorized();
        if (key == bytes32(0) || commitment == bytes32(0)) revert Invalid();
        if (latestVersion[org][key] != expectedVersion) revert StaleVersion();
        if (expectedVersion == 0 && correction) revert Invalid();
        Record storage prev = records[org][key][expectedVersion];
        if (expectedVersion > 0 && prev.kind != kind) revert Invalid();
        version = expectedVersion + 1;
        Record storage r = records[org][key][version];
        r.commitment = commitment; r.previous = prev.recordHash; r.author = msg.sender;
        r.recordedAt = uint64(block.timestamp); r.policyVersion = o.policyVersion; r.quorum = o.quorum;
        r.kind = kind; r.correction = correction;
        r.recordHash = _hash(org, key, version, r);
        recordSigners[r.recordHash] = policySigners[org]; latestVersion[org][key] = version;
        _emitRecorded(org, key, version, r);
    }
    function _hash(uint256 org, bytes32 key, uint256 version, Record storage r) private view returns(bytes32) {
        bytes32 policy = keccak256(abi.encode(r.policyVersion, policySigners[org], r.quorum));
        bytes32 payload = keccak256(abi.encode(r.commitment, r.previous, r.kind, r.correction));
        return keccak256(abi.encode(block.chainid, address(this), org, key, version, payload, policy));
    }
    function _emitRecorded(uint256 org, bytes32 key, uint256 version, Record storage r) private {
        emit Recorded(org, key, version, r.recordHash, r.commitment, r.previous, r.kind, r.correction, r.author);
    }

    /// @notice Attest or withdraw YOUR OWN attestation. Both transitions emit permanent events.
    function attest(uint256 org, bytes32 key, uint256 version, bytes32 expectedRecordHash, bool approve) external {
        Record storage r = records[org][key][version];
        if (r.recordHash == bytes32(0) || r.recordHash != expectedRecordHash) revert Invalid();
        address[] storage signers = recordSigners[r.recordHash]; bool allowed;
        for (uint256 i; i < signers.length; ++i) if (signers[i] == msg.sender) { allowed = true; break; }
        if (!allowed) revert Unauthorized();
        if (approvedBy[r.recordHash][msg.sender] == approve) revert Invalid();
        approvedBy[r.recordHash][msg.sender] = approve;
        if (approve) ++r.approvals; else --r.approvals;
        emit Attested(r.recordHash, msg.sender, approve, r.approvals);
    }
    function isApproved(uint256 org, bytes32 key, uint256 version) external view returns (bool) {
        Record storage r = records[org][key][version]; return r.quorum > 0 && r.approvals >= r.quorum;
    }
    function _controller(uint256 org) private view { if (organizations[org].controller != msg.sender) revert Unauthorized(); }
}
