// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
/// @notice TEST ONLY. Freely mintable; never use as a production settlement asset.
contract TestToken is ERC20 {
    bool public taxed;
    bool public blocked;
    constructor() ERC20("OPC Demo Token", "DEMO") {}
    function mint(address to, uint256 amount) external { _mint(to, amount); }
    function setTaxed(bool value) external { taxed = value; }
    function setBlocked(bool value) external { blocked = value; }
    function _update(address from, address to, uint256 amount) internal override {
        require(!blocked, "blocked");
        if (taxed && from != address(0) && to != address(0)) {
            uint256 tax = amount / 100;
            super._update(from, address(0), tax);
            amount -= tax;
        }
        super._update(from, to, amount);
    }
}
