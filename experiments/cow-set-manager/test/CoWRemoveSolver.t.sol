// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice One-off fork experiment for CoW removeSolver authorization.
/// @dev No forge-std dependency. Results are written to cow-remove-solver-evidence.json.
interface VmRemoveSolver {
    function createSelectFork(string calldata url, uint256 blockNumber) external returns (uint256);
    function prank(address msgSender) external;
    function load(address target, bytes32 slot) external view returns (bytes32);
    function envOr(string calldata name, uint256 defaultValue) external returns (uint256);
    function writeFile(string calldata path, string calldata data) external;
    function toString(address value) external pure returns (string memory);
    function toString(uint256 value) external pure returns (string memory);
}

contract CoWRemoveSolverTest {
    VmRemoveSolver private constant vm = VmRemoveSolver(address(uint160(uint256(keccak256("hevm cheat code")))));

    address private constant PROXY = 0xbbfB9a525ACdd2aB3A5Eb5fc9Ab8CF53b881000e;
    address private constant EXPECTED_IMPLEMENTATION = 0xFeDbc87123caF3925145e1bD1Be844c03b36722f;
    address private constant EXPECTED_INITIAL_MANAGER = 0x6Fb5916c0f57f88004d5b5EB25f6f4D77353a1eD;
    bytes32 private constant IMPLEMENTATION_SLOT =
        0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;
    bytes4 private constant ERROR_STRING_SELECTOR = 0x08c379a0;

    function testRemoveSolverManagerAllowedUnrelatedRejected() external {
        string memory rpc = _rpcUrl();
        uint256 forkBlock = vm.envOr("FORK_BLOCK_NUMBER", uint256(0));
        require(forkBlock != 0, "FORK_BLOCK_NUMBER missing");
        vm.createSelectFork(rpc, forkBlock);

        uint256 chainId = block.chainid;
        address implementation = address(uint160(uint256(vm.load(PROXY, IMPLEMENTATION_SLOT))));
        (bool managerReadOk, bytes memory managerData) = PROXY.staticcall(abi.encodeWithSignature("manager()"));
        require(managerReadOk && managerData.length >= 32, "manager() read failed");
        address manager = abi.decode(managerData, (address));
        bool implementationMatches = implementation == EXPECTED_IMPLEMENTATION;
        bool initialManagerMatches = manager == EXPECTED_INITIAL_MANAGER;
        require(chainId == 1, "wrong chain");

        address managerRemovedSolver = address(0xA11CE);
        address unrelatedAttemptSolver = address(0xCAFE);

        // Set up both solver memberships through the authorized manager.
        vm.prank(manager);
        (bool addAOk,) = PROXY.call(abi.encodeWithSignature("addSolver(address)", managerRemovedSolver));
        vm.prank(manager);
        (bool addBOk,) = PROXY.call(abi.encodeWithSignature("addSolver(address)", unrelatedAttemptSolver));
        require(addAOk && addBOk, "manager setup addSolver failed");
        bool managerSolverBefore = _isSolver(managerRemovedSolver);
        bool unrelatedSolverBefore = _isSolver(unrelatedAttemptSolver);
        require(managerSolverBefore && unrelatedSolverBefore, "solver setup membership missing");

        vm.prank(manager);
        (bool managerOk, bytes memory managerRet) =
            PROXY.call(abi.encodeWithSignature("removeSolver(address)", managerRemovedSolver));
        bool managerSolverAfter = _isSolver(managerRemovedSolver);

        address unrelated = address(0xBEEF);
        vm.prank(unrelated);
        (bool unrelatedOk, bytes memory unrelatedRet) =
            PROXY.call(abi.encodeWithSignature("removeSolver(address)", unrelatedAttemptSolver));
        string memory revertString = _decodeErrorString(unrelatedRet);
        bool revertMatchesGuard = !unrelatedOk &&
            keccak256(bytes(revertString)) == keccak256(bytes("GPv2: caller not manager"));
        bool unrelatedSolverAfter = _isSolver(unrelatedAttemptSolver);

        string memory judgment;
        if (!implementationMatches || !initialManagerMatches || !managerOk ||
            managerSolverBefore != true || managerSolverAfter != false || unrelatedSolverBefore != true) {
            judgment = "inconclusive";
        } else if (unrelatedOk) {
            judgment = "supported";
        } else if (revertMatchesGuard && unrelatedSolverAfter) {
            judgment = "rejected";
        } else {
            judgment = "inconclusive";
        }

        string memory evidence = string.concat(
            "{\n",
            '  "chain_id": ', vm.toString(chainId), ",\n",
            '  "fork_block": ', vm.toString(forkBlock), ",\n",
            '  "proxy": "', vm.toString(PROXY), '",\n',
            '  "implementation": "', vm.toString(implementation), '",\n',
            '  "implementation_address_matches_expected": ', implementationMatches ? "true" : "false", ",\n",
            '  "manager": "', vm.toString(manager), '",\n',
            '  "initial_manager_matches_expected": ', initialManagerMatches ? "true" : "false", ",\n",
            '  "guard_expected_from_source": "GPv2: caller not manager",\n',
            '  "caller_manager": { "address": "', vm.toString(manager),
            '", "outcome": "', managerOk ? "success" : "reverted",
            '", "removed_solver": "', vm.toString(managerRemovedSolver),
            '", "solver_allowed_before": ', managerSolverBefore ? "true" : "false",
            ', "solver_allowed_after": ', managerSolverAfter ? "true" : "false",
            ', "return_or_revert_data": "', _hex(managerRet), '" },\n',
            '  "caller_unrelated": { "address": "', vm.toString(unrelated),
            '", "outcome": "', unrelatedOk ? "success" : "reverted",
            '", "attempted_solver": "', vm.toString(unrelatedAttemptSolver),
            '", "solver_allowed_before": ', unrelatedSolverBefore ? "true" : "false",
            ', "revert_string": "', revertString,
            '", "revert_matches_guard": ', revertMatchesGuard ? "true" : "false",
            ', "solver_allowed_after": ', unrelatedSolverAfter ? "true" : "false",
            ', "return_or_revert_data": "', _hex(unrelatedRet), '" },\n',
            '  "judgment": "', judgment, '"\n',
            "}\n"
        );
        vm.writeFile("cow-remove-solver-evidence.json", evidence);
    }

    function _isSolver(address solver) private view returns (bool value) {
        (bool ok, bytes memory data) = PROXY.staticcall(abi.encodeWithSignature("isSolver(address)", solver));
        require(ok && data.length >= 32, "isSolver() read failed");
        value = abi.decode(data, (bool));
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
        (bool ok, bytes memory result) = address(vm).staticcall(
            abi.encodeWithSignature("envOr(string,string)", "MAINNET_RPC_URL", "")
        );
        if (ok && result.length > 0) {
            string memory configured = abi.decode(result, (string));
            if (bytes(configured).length > 0) return configured;
        }
        return "https://ethereum.publicnode.com";
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
