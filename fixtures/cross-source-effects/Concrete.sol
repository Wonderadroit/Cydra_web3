// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "./AbstractParent.sol";

contract Concrete is AbstractParent {
    function addValidator(uint256 id, address a) public {
        if (_map[id][a]) { return; }
        _add(id, a);
        _init(a);
    }
}
