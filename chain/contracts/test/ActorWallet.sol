// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
/// @notice Minimal contract-wallet fixture, NOT a production account abstraction implementation.
contract ActorWallet {
    address public immutable controller;
    constructor(address account) { controller = account; }
    function execute(address target, bytes calldata data) external returns(bytes memory) {
        require(msg.sender == controller, "controller");
        (bool success, bytes memory result) = target.call(data);
        if (!success) assembly { revert(add(result, 32), mload(result)) }
        return result;
    }
}
