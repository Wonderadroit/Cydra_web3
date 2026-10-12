// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.22;

contract VulnerableAuthorityRuntime {
    bytes32 public constant DEFAULT_ADMIN_ROLE = bytes32(0);
    mapping(bytes32 => mapping(address => bool)) private _roles;
    function hasRole(bytes32 role, address account) external view returns (bool) {
        return _roles[role][account];
    }
    function setTarget(address) external {
        _roles[DEFAULT_ADMIN_ROLE][msg.sender] = true;
    }
}

contract PermissionlessFactoryRuntime {
    mapping(address => bool) private _isChild;
    function create() external returns (address child) {
        child = address(new PermissionlessChildRuntime());
        _isChild[child] = true;
    }
    function isChild(address child) external view returns (bool) { return _isChild[child]; }
}
contract PermissionlessChildRuntime {}

contract GuardedAuthorityRuntime {
    bytes32 public constant DEFAULT_ADMIN_ROLE = bytes32(0);
    mapping(bytes32 => mapping(address => bool)) private _roles;
    address public immutable owner;
    constructor() { owner = msg.sender; _roles[DEFAULT_ADMIN_ROLE][msg.sender] = true; }
    function hasRole(bytes32 role, address account) external view returns (bool) {
        return _roles[role][account];
    }
    function setTarget(address) external {
        require(msg.sender == owner, "guarded: only owner");
        _roles[DEFAULT_ADMIN_ROLE][msg.sender] = true;
    }
}

contract BrokenSetupRuntime {
    constructor() { revert("broken: constructor failed"); }
}

contract RuntimeCaller {
    function callTarget(address target, bytes calldata payload) external returns (bool, bytes memory) {
        return target.call(payload);
    }
}
