// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.22;

contract GuardedAuthorityRuntime {
    bytes32 public constant DEFAULT_ADMIN_ROLE = bytes32(0);
    mapping(bytes32 => mapping(address => bool)) private _roles;
    address public immutable owner;

    constructor() {
        owner = msg.sender;
        _roles[DEFAULT_ADMIN_ROLE][msg.sender] = true;
    }

    function hasRole(bytes32 role, address account) external view returns (bool) {
        return _roles[role][account];
    }

    function setTarget(address) external {
        require(msg.sender == owner, "guarded: only owner");
        _roles[DEFAULT_ADMIN_ROLE][msg.sender] = true;
    }
}
