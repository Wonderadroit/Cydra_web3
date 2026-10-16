// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

abstract contract AbstractParent {
    mapping(uint256 => mapping(address => bool)) internal _map;
    uint256[] internal _list;
    mapping(address => uint256) internal _score;

    function _add(uint256 id, address a) internal {
        _map[id][a] = true;
        _list.push(id);
    }

    function _init(address a) internal {
        _score[a] = 1;
    }
}
