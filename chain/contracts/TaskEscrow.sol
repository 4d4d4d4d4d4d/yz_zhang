// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";

/// @notice Non-upgradeable, single-token escrow. No administrator withdrawal or arbitration override.
/// @dev Only ordinary non-rebasing, non-taxed ERC20 tokens are supported. Hashes MUST NOT contain raw personal data.
contract TaskEscrow is ReentrancyGuard, Ownable2Step, Pausable {
    using SafeERC20 for IERC20;
    enum State { Missing, Offered, Accepted, Funded, Closed }
    enum Stage { Pending, Delivered, Disputed, Settled }
    struct Terms {
        address executor;
        address arbitrator;
        bytes32 agreementHash;
        bytes32 platformRef;
        uint64 fundingDeadline;
        uint32 reviewPeriod;
        uint32 arbitrationPeriod;
        uint16 timeoutExecutorBps;
    }
    struct Job {
        address requester;
        Terms terms;
        bytes32 termsHash;
        State state;
        uint32 current;
        uint32 count;
        uint256 total;
        uint256 remaining;
        uint256 revision;
    }
    struct Milestone {
        uint256 amount;
        uint64 due;
        uint64 reviewDeadline;
        uint64 arbitrationDeadline;
        Stage stage;
        bytes32 delivery;
        bytes32 dispute;
    }
    struct Delegate { address account; uint64 expires; }
    struct Cancellation { address proposer; uint256 executorAmount; uint256 revision; uint64 expires; }
    IERC20 public immutable token;
    address public immutable feeRecipient;
    uint16 public immutable feeBps;
    uint256 public nextId = 1;
    uint256 public totalEscrowed;
    uint256 public totalCredits;
    mapping(uint256 => Job) private jobs;
    mapping(uint256 => mapping(uint256 => Milestone)) public milestones;
    mapping(uint256 => Delegate) public delegates;
    mapping(uint256 => Cancellation) public cancellations;
    mapping(address => uint256) public credits;
    error Invalid();
    error Unauthorized();
    error WrongState();
    error Deadline();
    event Created(uint256 indexed id, address indexed requester, address indexed executor, bytes32 termsHash, bytes32 platformRef);
    event Accepted(uint256 indexed id, bytes32 termsHash);
    event Funded(uint256 indexed id, uint256 amount);
    event Delivered(uint256 indexed id, uint256 indexed index, bytes32 digest, uint64 reviewDeadline);
    event Disputed(uint256 indexed id, uint256 indexed index, bytes32 digest, uint64 deadline);
    event Settled(uint256 indexed id, uint256 indexed index, uint256 executorGross, uint256 requesterRefund, uint256 fee, bytes32 decision);
    event Closed(uint256 indexed id, uint256 executorGross, uint256 requesterRefund, bytes32 reason);
    event CancellationProposed(uint256 indexed id, address proposer, uint256 executorAmount, uint256 revision, uint64 expires);
    event DelegateSet(uint256 indexed id, address account, uint64 expires);
    event Withdrawn(address indexed account, uint256 amount);

    constructor(address administrator, IERC20 settlementToken, address recipient, uint16 bps) Ownable(administrator) {
        if (address(settlementToken).code.length == 0 || recipient == address(0) || bps > 1000) revert Invalid();
        token = settlementToken; feeRecipient = recipient; feeBps = bps;
    }
    function setPaused(bool value) external onlyOwner { if (value) _pause(); else _unpause(); }
    function renounceOwnership() public override onlyOwner { revert Invalid(); }
    function getJob(uint256 id) external view returns (Job memory) { return jobs[id]; }

    /// @dev termsHash commits to every economic parameter, chain, instance, and identity; no mutable off-chain terms.
    function create(Terms calldata terms, uint256[] calldata amounts, uint64[] calldata dues) external whenNotPaused returns (uint256 id) {
        if (terms.executor == address(0) || terms.executor == msg.sender || terms.arbitrator == address(0)
            || terms.arbitrator == msg.sender || terms.arbitrator == terms.executor || terms.agreementHash == bytes32(0)
            || terms.platformRef == bytes32(0) || terms.fundingDeadline <= block.timestamp
            || terms.reviewPeriod < 1 hours || terms.reviewPeriod > 30 days
            || terms.arbitrationPeriod < 1 days || terms.arbitrationPeriod > 90 days
            || terms.timeoutExecutorBps > 10000 || amounts.length == 0 || amounts.length > 32 || amounts.length != dues.length) revert Invalid();
        id = nextId++;
        Job storage j = jobs[id];
        j.requester = msg.sender; j.terms = terms; j.state = State.Offered; j.count = uint32(amounts.length);
        uint64 previous = terms.fundingDeadline;
        for (uint256 i; i < amounts.length; ++i) {
            if (amounts[i] == 0 || dues[i] <= previous) revert Invalid();
            milestones[id][i].amount = amounts[i]; milestones[id][i].due = dues[i];
            j.total += amounts[i]; previous = dues[i];
        }
        j.termsHash = keccak256(abi.encode(block.chainid, address(this), id, msg.sender, terms, amounts, dues, address(token), feeRecipient, feeBps));
        emit Created(id, msg.sender, terms.executor, j.termsHash, terms.platformRef);
    }
    function accept(uint256 id, bytes32 expectedTermsHash) external {
        Job storage j = jobs[id];
        if (msg.sender != j.terms.executor) revert Unauthorized();
        if (j.state != State.Offered || expectedTermsHash != j.termsHash) revert WrongState();
        if (block.timestamp > j.terms.fundingDeadline) revert Deadline();
        j.state = State.Accepted; ++j.revision; emit Accepted(id, j.termsHash);
    }
    function fund(uint256 id) external nonReentrant whenNotPaused {
        Job storage j = jobs[id];
        if (msg.sender != j.requester) revert Unauthorized();
        if (j.state != State.Accepted) revert WrongState();
        if (block.timestamp > j.terms.fundingDeadline) revert Deadline();
        j.state = State.Funded; j.remaining = j.total; totalEscrowed += j.total; ++j.revision;
        uint256 beforeBalance = token.balanceOf(address(this));
        token.safeTransferFrom(msg.sender, address(this), j.total);
        if (token.balanceOf(address(this)) - beforeBalance != j.total) revert Invalid();
        emit Funded(id, j.total);
    }
    function closeUnfunded(uint256 id) external {
        Job storage j = jobs[id];
        if (j.state != State.Offered && j.state != State.Accepted) revert WrongState();
        if (msg.sender != j.requester && block.timestamp <= j.terms.fundingDeadline) revert Unauthorized();
        j.state = State.Closed; ++j.revision; emit Closed(id, 0, 0, keccak256("UNFUNDED"));
    }
    /// @notice A machine delegate may ONLY submit evidence, never accept work or move funds.
    function setDelegate(uint256 id, address account, uint64 expires) external {
        Job storage j = jobs[id];
        if (msg.sender != j.terms.executor) revert Unauthorized();
        if (j.state == State.Closed) revert WrongState();
        if (account != address(0) && (expires <= block.timestamp || expires > block.timestamp + 90 days)) revert Invalid();
        delegates[id] = Delegate(account, expires); emit DelegateSet(id, account, expires);
    }
    function deliver(uint256 id, bytes32 digest) external {
        Job storage j = jobs[id]; Delegate memory d = delegates[id];
        if (msg.sender != j.terms.executor && (msg.sender != d.account || block.timestamp > d.expires)) revert Unauthorized();
        Milestone storage m = _active(j, id);
        if (m.stage != Stage.Pending || digest == bytes32(0)) revert WrongState();
        if (block.timestamp > m.due) revert Deadline();
        m.stage = Stage.Delivered; m.delivery = digest; m.reviewDeadline = uint64(block.timestamp + j.terms.reviewPeriod);
        ++j.revision; emit Delivered(id, j.current, digest, m.reviewDeadline);
    }
    function approve(uint256 id) external {
        Job storage j = jobs[id];
        if (msg.sender != j.requester) revert Unauthorized();
        Milestone storage m = _active(j, id);
        if (m.stage != Stage.Delivered) revert WrongState();
        _settle(id, j, m, m.amount, keccak256("APPROVED"));
    }
    function releaseAfterReview(uint256 id) external {
        Job storage j = jobs[id]; Milestone storage m = _active(j, id);
        if (m.stage != Stage.Delivered) revert WrongState();
        if (block.timestamp <= m.reviewDeadline) revert Deadline();
        _settle(id, j, m, m.amount, keccak256("REVIEW_EXPIRED"));
    }
    function dispute(uint256 id, bytes32 digest) external {
        Job storage j = jobs[id];
        if (msg.sender != j.requester && msg.sender != j.terms.executor) revert Unauthorized();
        Milestone storage m = _active(j, id);
        if (m.stage != Stage.Delivered || digest == bytes32(0)) revert WrongState();
        if (block.timestamp > m.reviewDeadline) revert Deadline();
        m.stage = Stage.Disputed; m.dispute = digest;
        m.arbitrationDeadline = uint64(block.timestamp + j.terms.arbitrationPeriod); ++j.revision;
        emit Disputed(id, j.current, digest, m.arbitrationDeadline);
    }
    function resolve(uint256 id, uint256 executorGross, bytes32 decision) external {
        Job storage j = jobs[id];
        if (msg.sender != j.terms.arbitrator) revert Unauthorized();
        Milestone storage m = _active(j, id);
        if (m.stage != Stage.Disputed || executorGross > m.amount || decision == bytes32(0)) revert WrongState();
        if (block.timestamp > m.arbitrationDeadline) revert Deadline();
        _settle(id, j, m, executorGross, decision);
    }
    function resolveAfterTimeout(uint256 id) external {
        Job storage j = jobs[id]; Milestone storage m = _active(j, id);
        if (m.stage != Stage.Disputed) revert WrongState();
        if (block.timestamp <= m.arbitrationDeadline) revert Deadline();
        _settle(id, j, m, _bps(m.amount, j.terms.timeoutExecutorBps), keccak256("ARBITRATION_EXPIRED"));
    }
    /// @notice No delivery by the agreed deadline: refund all remaining, unearned milestones.
    function refundOverdue(uint256 id) external {
        Job storage j = jobs[id]; Milestone storage m = _active(j, id);
        if (m.stage != Stage.Pending) revert WrongState();
        if (block.timestamp <= m.due) revert Deadline();
        _close(id, j, 0, keccak256("DELIVERY_EXPIRED"));
    }
    function proposeCancellation(uint256 id, uint256 executorGross, uint64 expires) external {
        Job storage j = jobs[id];
        if (msg.sender != j.requester && msg.sender != j.terms.executor) revert Unauthorized();
        if (j.state != State.Funded || executorGross > j.remaining || expires <= block.timestamp || expires > block.timestamp + 7 days) revert Invalid();
        // Bump on EVERY proposal; a replacement can never reuse the reviewed proposal revision.
        ++j.revision;
        cancellations[id] = Cancellation(msg.sender, executorGross, j.revision, expires);
        emit CancellationProposed(id, msg.sender, executorGross, j.revision, expires);
    }
    function acceptCancellation(uint256 id, uint256 revision, uint256 expectedExecutorGross) external {
        Job storage j = jobs[id]; Cancellation memory c = cancellations[id];
        if (msg.sender != j.requester && msg.sender != j.terms.executor) revert Unauthorized();
        if (msg.sender == c.proposer || c.proposer == address(0)) revert Unauthorized();
        if (j.state != State.Funded || revision != j.revision || c.revision != revision || c.executorAmount != expectedExecutorGross) revert WrongState();
        if (block.timestamp > c.expires) revert Deadline();
        _close(id, j, c.executorAmount, keccak256("MUTUAL_CANCELLATION"));
    }
    function withdraw() external nonReentrant {
        uint256 amount = credits[msg.sender];
        if (amount == 0) revert Invalid();
        credits[msg.sender] = 0; totalCredits -= amount;
        token.safeTransfer(msg.sender, amount); emit Withdrawn(msg.sender, amount);
    }
    function _active(Job storage j, uint256 id) private view returns (Milestone storage) {
        if (j.state != State.Funded || j.current >= j.count) revert WrongState();
        return milestones[id][j.current];
    }
    // Overflow-safe basis-point calculation, including deliberately adversarial token denominations.
    function _bps(uint256 amount, uint256 bps) private pure returns (uint256) { return amount / 10000 * bps + amount % 10000 * bps / 10000; }
    function _credit(Job storage j, uint256 amount, uint256 executorGross) private returns (uint256 fee) {
        fee = _bps(executorGross, feeBps);
        credits[j.terms.executor] += executorGross - fee;
        credits[j.requester] += amount - executorGross;
        credits[feeRecipient] += fee;
        totalEscrowed -= amount; totalCredits += amount; j.remaining -= amount;
    }
    function _settle(uint256 id, Job storage j, Milestone storage m, uint256 gross, bytes32 decision) private {
        m.stage = Stage.Settled;
        uint256 fee = _credit(j, m.amount, gross);
        emit Settled(id, j.current, gross, m.amount - gross, fee, decision);
        ++j.current; ++j.revision;
        if (j.current == j.count) { j.state = State.Closed; emit Closed(id, 0, 0, keccak256("COMPLETED")); }
    }
    function _close(uint256 id, Job storage j, uint256 gross, bytes32 reason) private {
        uint256 remaining = j.remaining;
        _credit(j, remaining, gross); j.state = State.Closed; ++j.revision;
        emit Closed(id, gross, remaining - gross, reason);
    }
}
