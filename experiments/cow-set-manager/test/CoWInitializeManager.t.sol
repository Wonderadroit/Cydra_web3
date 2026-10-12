// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice Fork experiment for re-invocation of CoW's manager initializer.
/// @dev A successful unauthorized manager overwrite is a candidate; unknown reverts are inconclusive.
interface VmInitializeManager {
    function createSelectFork(string calldata url, uint256 blockNumber) external returns (uint256);
    function prank(address msgSender) external;
    function load(address target, bytes32 slot) external view returns (bytes32);
    function envOr(string calldata name, uint256 defaultValue) external returns (uint256);
    function writeFile(string calldata path, string calldata data) external;
    function toString(address value) external pure returns (string memory);
    function toString(uint256 value) external pure returns (string memory);
}

contract CoWInitializeManagerTest {
    VmInitializeManager private constant vm =
        VmInitializeManager(address(uint160(uint256(keccak256("hevm cheat code")))));

    address private constant PROXY = 0xbbfB9a525ACdd2aB3A5Eb5fc9Ab8CF53b881000e;
    address private constant EXPECTED_IMPLEMENTATION = 0xFeDbc87123caF3925145e1bD1Be844c03b36722f;
    address private constant EXPECTED_INITIAL_MANAGER = 0x6Fb5916c0f57f88004d5b5EB25f6f4D77353a1eD;
    bytes32 private constant IMPLEMENTATION_SLOT =
        0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;
    bytes4 private constant ERROR_STRING_SELECTOR = 0x08c379a0;

    function testInitializeManagerCannotBeReplayedByUnrelatedCaller() external {
        string memory rpc = _rpcUrl();
        uint256 forkBlock = vm.envOr("FORK_BLOCK_NUMBER", uint256(0));
        require(forkBlock != 0, "FORK_BLOCK_NUMBER missing");
        vm.createSelectFork(rpc, forkBlock);
        require(block.chainid == 1, "wrong chain");

        address implementation = address(uint160(uint256(vm.load(PROXY, IMPLEMENTATION_SLOT))));
        (bool readOk, bytes memory beforeData) = PROXY.staticcall(abi.encodeWithSignature("manager()"));
        require(readOk && beforeData.length >= 32, "manager() read failed");
        address managerBefore = abi.decode(beforeData, (address));

        address unrelated = address(0xBEEF);
        address attemptedManager = address(0xBAD);
        vm.prank(unrelated);
        (bool callOk, bytes memory returnData) =
            PROXY.call(abi.encodeWithSignature("initializeManager(address)", attemptedManager));

        (bool afterReadOk, bytes memory afterData) = PROXY.staticcall(abi.encodeWithSignature("manager()"));
        require(afterReadOk && afterData.length >= 32, "manager() after read failed");
        address managerAfter = abi.decode(afterData, (address));
        string memory revertString = _decodeErrorString(returnData);
        bool implementationMatches = implementation == EXPECTED_IMPLEMENTATION;
        bool initialManagerMatches = managerBefore == EXPECTED_INITIAL_MANAGER;
        bool stateUnchanged = managerAfter == managerBefore;
        bool expectedInitializedGuard = !callOk &&
            keccak256(bytes(revertString)) == keccak256(bytes("Initializable: contract is already initialized"));

        string memory judgment;
        if (!implementationMatches || !initialManagerMatches) {
            judgment = "inconclusive";
        } else if (callOk && managerAfter == attemptedManager) {
            judgment = "supported";
        } else if (expectedInitializedGuard && stateUnchanged) {
            judgment = "rejected";
        } else {
            judgment = "inconclusive";
        }

        string memory evidence = string.concat(
            "{\n",
            '  "chain_id": ', vm.toString(block.chainid), ",\n",
            '  "fork_block": ', vm.toString(forkBlock), ",\n",
            '  "proxy": "', vm.toString(PROXY), '",\n',
            '  "implementation": "', vm.toString(implementation), '",\n',
            '  "implementation_address_matches_expected": ', implementationMatches ? "true" : "false", ",\n",
            '  "manager_before": "', vm.toString(managerBefore), '",\n',
            '  "initial_manager_matches_expected": ', initialManagerMatches ? "true" : "false", ",\n",
            '  "caller_unrelated": "', vm.toString(unrelated), '",\n',
            '  "attempted_manager": "', vm.toString(attemptedManager), '",\n',
            '  "call_outcome": "', callOk ? "success" : "reverted", '",\n',
            '  "revert_string": "', revertString, '",\n',
            '  "revert_matches_initialized_guard": ', expectedInitializedGuard ? "true" : "false", ",\n",
            '  "manager_after": "', vm.toString(managerAfter), '",\n',
            '  "manager_state_unchanged": ', stateUnchanged ? "true" : "false", ",\n",
            '  "return_or_revert_data": "', _hex(returnData), '",\n',
            '  "judgment": "', judgment, '"\n',
            "}\n"
        );
        vm.writeFile("cow-initialize-manager-evidence.json", evidence);
    }

    function _rpcUrl() private returns (string memory) {
        (bool ok, bytes memory result) = address(vm).staticcall(
            abi.encodeWithSignature("envOr(string,string)", "MAINNET_RPC_URL", "")
        );
        if (ok && result.length > 0) {
            string memory configured = abi.decode(result, (string));
            if (bytes(configured).length > 0) return configured;
        }
        return "https://ethereum.publicnode.com";
    }

    function _decodeErrorString(bytes memory data) private pure returns (string memory) {
        if (data.length < 68) return "";
        bytes4 selector;
        assembly ("memory-safe") { selector := mload(add(data, 32)) }
        if (selector != ERROR_STRING_SELECTOR) return "";
        bytes memory payload = new bytes(data.length - 4);
        for (uint256 i; i < payload.length; ++i) payload[i] = data[i + 4];
        return abi.decode(payload, (string));
    }

    function _hex(bytes memory data) private pure returns (string memory) {
        bytes16 alphabet = "0123456789abcdef";
        bytes memory out = new bytes(2 + data.length * 2);
        out[0] = "0";
        out[1] = "x";
        for (uint256 i; i < data.length; ++i) {
            out[2 + i * 2] = alphabet[uint8(data[i] >> 4)];
            out[3 + i * 2] = alphabet[uint8(data[i] & 0x0f)];
        }
        return string(out);
    }
}
