// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.22;

contract BrokenSetupRuntime {
    constructor() {
        revert("broken: constructor failed");
    }

    function setTarget(address) external {}
}
