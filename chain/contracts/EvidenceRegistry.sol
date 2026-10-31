// SPDX-License-Identifier: MIT
pragma solidity ^0.8.30;

import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";

/// @notice Anchors platform audit-chain checkpoints. No personal data or money.
/// @dev A checkpoint proves publication of a digest, not truth of its source data.
contract EvidenceRegistry is Ownable2Step {
    struct Checkpoint { uint256 first; bytes32 digest; uint256 recordedAt; }
    mapping(uint256 => Checkpoint) public checkpoints;
    uint256 public lastSequence;
    address public publisher;
    bool public paused;
    event Anchored(uint256 indexed first, uint256 indexed last, bytes32 indexed digest);
    event PublisherChanged(address indexed publisher);
    event PauseChanged(bool paused);
    error Unauthorized();
    error InvalidCheckpoint();
    error PublicationPaused();

    constructor(address administrator, address initialPublisher) Ownable(administrator) {
        if (initialPublisher == address(0)) revert Unauthorized();
        publisher = initialPublisher;
    }
    function setPublisher(address next) external onlyOwner {
        if (next == address(0)) revert Unauthorized();
        publisher = next;
        emit PublisherChanged(next);
    }
    function setPaused(bool value) external onlyOwner {
        paused = value;
        emit PauseChanged(value);
    }
    function anchor(uint256 first, uint256 last, bytes32 digest) external {
        if (msg.sender != publisher) revert Unauthorized();
        if (paused) revert PublicationPaused();
        if (first != lastSequence + 1 || last < first || digest == bytes32(0))
            revert InvalidCheckpoint();
        checkpoints[last] = Checkpoint(first, digest, block.timestamp);
        lastSequence = last;
        emit Anchored(first, last, digest);
    }
    /// @dev Prevent accidental destruction of administrative recovery rights.
    function renounceOwnership() public override onlyOwner { revert Unauthorized(); }
}
