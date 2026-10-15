// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

abstract contract AbstractParent {
    function parentReady() public pure virtual returns (bool) {
        return true;
    }
}
