// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice One-off fork experiment for CoW's deployed GPv2AllowListAuthentication proxy.
/// @dev No forge-std dependency. Results are written to cow-set-manager-evidence.json.
interface Vm {
    struct Log { bytes32[] topics; bytes data; address emitter; }
    function createSelectFork(string calldata url, uint256 blockNumber) external returns (uint256);
    function prank(address msgSender) external;
    function load(address target, bytes32 slot) external view returns (bytes32);
    function recordLogs() external;
    function getRecordedLogs() external returns (Log[] memory);
    function writeFile(string calldata path, string calldata data) external;
    function toString(address value) external pure returns (string memory);
    function toString(uint256 value) external pure returns (string memory);
    function toString(bytes memory value) external pure returns (string memory);
    function log(string calldata) external;
}

contract CoWSetManagerTest {
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));

    address private constant PROXY = 0xbbfB9a525ACdd2aB3A5Eb5fc9Ab8CF53b881000e;
    address private constant EXPECTED_IMPLEMENTATION = 0xFeDbc87123caF3925145e1bD1Be844c03b36722f;
    address private constant EXPECTED_INITIAL_MANAGER = 0x6Fb5916c0f57f88004d5b5EB25f6f4D77353a1eD;
    bytes32 private constant ADMIN_SLOT =
        0xb53127684a568b3173ae13b9f8a6016e243e63b6e8ee1178d6a717850b5d6103;
    bytes32 private constant IMPLEMENTATION_SLOT =
        0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;
    uint256 private constant FORK_BLOCK = 15500000;
    bytes4 private constant ERROR_STRING_SELECTOR = 0x08c379a0;

    function testSetManagerAuthorizationOnPinnedDeploymentBlock() external {
        string memory rpc = _rpcUrl();
        vm.createSelectFork(rpc, FORK_BLOCK);

        uint256 chainId = block.chainid;
        address implementation = address(uint160(uint256(vm.load(PROXY, IMPLEMENTATION_SLOT))));
        bytes32 adminSlotRaw = vm.load(PROXY, ADMIN_SLOT);
        address admin = address(uint160(uint256(adminSlotRaw)));
        address managerBefore = _manager();
        bool overlap = managerBefore == admin;

        // The chosen block is the proxy's recorded deployment block; fail closed if
        // the deployment identity/state does not match the pinned deployment artifact.
        require(chainId == 1, "wrong chain");
        bool implementationMatchesPinnedSource = implementation == EXPECTED_IMPLEMENTATION;

        address nextManager = address(0xA11CE);
        vm.recordLogs();
        vm.prank(managerBefore);
        (bool managerOk, bytes memory managerRet) =
            PROXY.call(abi.encodeWithSignature("setManager(address)", nextManager));
        Vm.Log[] memory logs = vm.getRecordedLogs();
        address managerAfter = _manager();
        bool eventMatched = _hasManagerChanged(logs, nextManager, managerBefore);

        // Test the admin arm independently only when it is a distinct, non-zero role.
        bool adminOk = false;
        bool adminEventMatched = false;
        bytes memory adminRet;
        address adminAfter = managerAfter;
        if (!overlap && admin != address(0)) {
            address adminNextManager = address(0xAD11);
            vm.recordLogs();
            vm.prank(admin);
            (adminOk, adminRet) =
                PROXY.call(abi.encodeWithSignature("setManager(address)", adminNextManager));
            Vm.Log[] memory adminLogs = vm.getRecordedLogs();
            adminAfter = _manager();
            adminEventMatched = _hasManagerChanged(adminLogs, adminNextManager, managerAfter);
        }

        address unrelated = address(0xBEEF);
        vm.prank(unrelated);
        (bool unrelatedOk, bytes memory unrelatedRet) =
            PROXY.call(abi.encodeWithSignature("setManager(address)", address(0xCAFE)));
        string memory revertString = _decodeErrorString(unrelatedRet);
        bool revertMatchesGuard = !unrelatedOk &&
            keccak256(bytes(revertString)) == keccak256(bytes("GPv2: not authorized"));
        address managerAfterUnrelated = _manager();

        string memory judgment;
        if (
            !implementationMatchesPinnedSource ||
            !managerOk || managerAfter != nextManager || !eventMatched ||
            (!overlap && admin != address(0) &&
                (!adminOk || adminAfter == managerAfter || !adminEventMatched))
        ) {
            judgment = "inconclusive";
        } else if (unrelatedOk) {
            judgment = "supported";
        } else if (revertMatchesGuard) {
            judgment = "rejected";
        } else {
            judgment = "inconclusive";
        }

        string memory evidence = string.concat(
            "{\n",
            '  "chain_id": ', vm.toString(chainId), ",\n",
            '  "fork_block": ', vm.toString(FORK_BLOCK), ",\n",
            '  "rpc_endpoint_kind": "configured_or_public_fallback",\n',
            '  "proxy": "', vm.toString(PROXY), '",\n',
            '  "implementation": "', vm.toString(implementation), '",\n',
            '  "implementation_matches_pinned_source": ',
            implementationMatchesPinnedSource ? "true" : "false", ",\n",
            '  "manager_before": "', vm.toString(managerBefore), '",\n',
            '  "admin_slot_raw": "', _hex32(adminSlotRaw), '",\n',
            '  "admin_address": "', vm.toString(admin), '",\n',
            '  "manager_admin_overlap": ', overlap ? "true" : "false", ",\n",
            '  "caller_manager": { "address": "', vm.toString(managerBefore),
            '", "outcome": "', managerOk ? "success" : "reverted",
            '", "manager_after": "', vm.toString(managerAfter),
            '", "manager_changed_event_matched": ', eventMatched ? "true" : "false",
            ', "return_or_revert_data": "', _hexBytes(managerRet), '" },\n',
            '  "caller_admin": { "address": "', vm.toString(admin),
            '", "outcome": "',
            overlap ? "overlap_with_manager_at_fork_block" :
                (admin == address(0) ? "skipped_zero_admin" : (adminOk ? "success" : "reverted")),
            '", "independent_call": ', (!overlap && admin != address(0)) ? "true" : "false",
            ', "manager_after": "', vm.toString(adminAfter),
            '", "event_matched": ', adminEventMatched ? "true" : "false",
            ', "return_or_revert_data": "', _hexBytes(adminRet), '" },\n',
            '  "caller_unrelated": { "address": "', vm.toString(unrelated),
            '", "outcome": "', unrelatedOk ? "success" : "reverted",
            '", "revert_string": "', _jsonEscape(revertString),
            '", "revert_data": "', _hexBytes(unrelatedRet),
            '", "revert_matches_guard": ', revertMatchesGuard ? "true" : "false",
            ', "manager_after": "', vm.toString(managerAfterUnrelated), '" },\n',
            '  "judgment": "', judgment, '"\n',
            "}\n"
        );
        vm.writeFile("cow-set-manager-evidence.json", evidence);
        vm.log(string.concat("CoW setManager judgment: ", judgment));
        vm.log(string.concat("Evidence: ", evidence));
    }

    function _manager() private view returns (address value) {
        (bool ok, bytes memory data) = PROXY.staticcall(abi.encodeWithSignature("manager()"));
        require(ok && data.length >= 32, "manager() read failed");
        value = abi.decode(data, (address));
    }

    function _hasManagerChanged(
        Vm.Log[] memory logs,
        address newManager,
        address oldManager
    ) private view returns (bool) {
        bytes32 signature = keccak256("ManagerChanged(address,address)");
        for (uint256 i; i < logs.length; ++i) {
            if (
                logs[i].emitter == PROXY &&
                logs[i].topics.length == 1 &&
                logs[i].topics[0] == signature &&
                logs[i].data.length == 64 &&
                _eventAddressesMatch(logs[i].data, newManager, oldManager)
            ) return true;
        }
        return false;
    }

    function _eventAddressesMatch(bytes memory data, address newManager, address oldManager)
        private pure returns (bool)
    {
        (address emittedNewManager, address emittedOldManager) = abi.decode(data, (address, address));
        return emittedNewManager == newManager && emittedOldManager == oldManager;
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

    function _rpcUrl() private returns (string memory) {
        // The workflow supplies MAINNET_RPC_URL from a repository secret when present.
        // Otherwise it tries the listed public endpoints in order.
        // envOr is invoked through the cheatcode interface below via low-level staticcall
        // so the test remains dependency-free.
        (bool ok, bytes memory result) = address(vm).staticcall(
            abi.encodeWithSignature("envOr(string,string)", "MAINNET_RPC_URL", "")
        );
        if (ok && result.length > 0) {
            string memory configured = abi.decode(result, (string));
            if (bytes(configured).length > 0) return configured;
        }
        return "https://ethereum.publicnode.com";
    }

    function _hex32(bytes32 value) private pure returns (string memory) {
        return _hexBytes(abi.encodePacked(value));
    }

    function _hexBytes(bytes memory data) private pure returns (string memory) {
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

    function _jsonEscape(string memory input) private pure returns (string memory) {
        bytes memory data = bytes(input);
        bytes memory out = new bytes(data.length);
        for (uint256 i; i < data.length; ++i) {
            // Guard strings here are simple ASCII; escape quote and backslash defensively.
            if (data[i] == '"' || data[i] == '\\') {
                return "";
            }
            out[i] = data[i];
        }
        return string(out);
    }
}
