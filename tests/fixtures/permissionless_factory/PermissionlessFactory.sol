// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.22;

/// @notice Calibration fixture: creating a child is permissionless by design.
contract PermissionlessChild {}

contract PermissionlessFactory {
    mapping(address => bool) private _isChild;

    function create() external returns (address child) {
        child = address(new PermissionlessChild());
        _isChild[child] = true;
    }

    function isChild(address child) external view returns (bool) {
        return _isChild[child];
    }
}
