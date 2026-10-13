// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.22;

/// Positive control: setTarget is intentionally unguarded and grants the caller
/// DEFAULT_ADMIN_ROLE on this already-existing contract resource.
contract VulnerableAuthority {
    bytes32 public constant DEFAULT_ADMIN_ROLE = bytes32(0);
    mapping(bytes32 => mapping(address => bool)) private _roles;
    address public target;

    function hasRole(bytes32 role, address account) external view returns (bool) {
        return _roles[role][account];
    }

    function setTarget(address newTarget) external {
        target = newTarget;
        _roles[DEFAULT_ADMIN_ROLE][msg.sender] = true;
    }
}
