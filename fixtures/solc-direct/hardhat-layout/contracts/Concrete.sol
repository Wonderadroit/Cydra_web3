// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AbstractParent.sol";

contract Concrete is AbstractParent {
    uint256 private state_A;
    uint256 private state_B;

    function addValidator(uint256 value) external {
        _addValidator(value);
    }

    function _addValidator(uint256 value) internal {
        state_A = value;
        _initValidatorScore(value + 1);
    }

    function _initValidatorScore(uint256 value) internal {
        state_B = value;
    }
}
