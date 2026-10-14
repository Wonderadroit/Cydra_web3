// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.22;

contract OwnableFixture {
    address private _owner;

    constructor() {
        _owner = msg.sender;
    }

    function owner() public view returns (address) {
        return _owner;
    }

    modifier onlyOwner() {
        require(msg.sender == _owner, "Ownable: caller is not the owner");
        _;
    }
}

contract StateControlFixture is OwnableFixture {
    address public router;
    address public treasury;

    // Deliberately unguarded: this must be detected as unauthorized state control.
    function setRouter(address nextRouter) external {
        router = nextRouter;
    }

    // Sibling comparison: privileged configuration setters are owner-gated.
    function setTreasury(address nextTreasury) external onlyOwner {
        treasury = nextTreasury;
    }
}

contract GuardedStateControlFixture is OwnableFixture {
    address public router;

    function setRouter(address nextRouter) external onlyOwner {
        router = nextRouter;
    }
}
