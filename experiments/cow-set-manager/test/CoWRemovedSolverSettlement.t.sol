// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @notice Cross-function authorization test against the authenticator actually configured by the deployed settlement.
/// @dev All writes occur on a local Ethereum mainnet fork; no live-chain transaction is broadcast.
interface VmCoWCrossFunction {
    function createSelectFork(string calldata url, uint256 blockNumber) external returns (uint256);
    function prank(address msgSender) external;
    function load(address target, bytes32 slot) external view returns (bytes32);
    function envOr(string calldata name, uint256 defaultValue) external returns (uint256);
    function writeFile(string calldata path, string calldata data) external;
    function toString(address value) external pure returns (string memory);
    function toString(uint256 value) external pure returns (string memory);
}

interface ICoWSettlementCrossFunction {
    struct Trade {
        uint256 sellTokenIndex;
        uint256 buyTokenIndex;
        address receiver;
        uint256 sellAmount;
        uint256 buyAmount;
        uint32 validTo;
        bytes32 appData;
        uint256 feeAmount;
        uint256 flags;
        uint256 executedAmount;
        bytes signature;
    }
    struct Interaction {
        address target;
        uint256 value;
        bytes callData;
    }
    function authenticator() external view returns (address);
    function settle(
        address[] calldata tokens,
        uint256[] calldata clearingPrices,
        Trade[] calldata trades,
        Interaction[][3] calldata interactions
    ) external;
}

contract CoWRemovedSolverSettlementTest {
    VmCoWCrossFunction private constant vm =
        VmCoWCrossFunction(address(uint160(uint256(keccak256("hevm cheat code")))));

    address private constant SETTLEMENT = 0x9008D19f58AAbD9eD0D60971565AA8510560ab41;
    bytes32 private constant IMPLEMENTATION_SLOT =
        0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc;
    bytes4 private constant ERROR_STRING_SELECTOR = 0x08c379a0;
    string private constant NOT_SOLVER = "GPv2: not a solver";

    function testRemovedSolverCannotPassSettlementAuthorization() external {
        uint256 forkBlock = vm.envOr("FORK_BLOCK_NUMBER", uint256(0));
        require(forkBlock != 0, "FORK_BLOCK_NUMBER missing");
        vm.createSelectFork(_rpcUrl(), forkBlock);
        require(block.chainid == 1, "wrong chain");

        (bool authReadOk, bytes memory authData) =
            SETTLEMENT.staticcall(abi.encodeWithSignature("authenticator()"));
        require(authReadOk && authData.length >= 32, "settlement authenticator read failed");
        address authenticator = abi.decode(authData, (address));
        require(authenticator != address(0) && authenticator.code.length > 0, "configured authenticator has no code");

        address implementation = address(uint160(uint256(vm.load(authenticator, IMPLEMENTATION_SLOT))));
        (bool managerReadOk, bytes memory managerData) =
            authenticator.staticcall(abi.encodeWithSignature("manager()"));
        require(managerReadOk && managerData.length >= 32, "configured manager() read failed");
        address manager = abi.decode(managerData, (address));
        require(manager != address(0), "configured manager is zero");

        address solver = address(0xA11CE);
        vm.prank(manager);
        (bool addOk, bytes memory addData) =
            authenticator.call(abi.encodeWithSignature("addSolver(address)", solver));
        bool solverAllowedBefore = _isSolver(authenticator, solver);

        address[] memory tokens = new address[](0);
        uint256[] memory prices = new uint256[](0);
        ICoWSettlementCrossFunction.Trade[] memory trades =
            new ICoWSettlementCrossFunction.Trade[](0);
        ICoWSettlementCrossFunction.Interaction[][3] memory interactions;

        vm.prank(solver);
        (bool beforeOk, bytes memory beforeData) = SETTLEMENT.call(
            abi.encodeWithSelector(
                ICoWSettlementCrossFunction.settle.selector,
                tokens, prices, trades, interactions
            )
        );
        string memory beforeReason = _decodeErrorString(beforeData);
        bool beforePassedSolverGate = beforeOk ||
            keccak256(bytes(beforeReason)) != keccak256(bytes(NOT_SOLVER));

        vm.prank(manager);
        (bool removeOk, bytes memory removeData) =
            authenticator.call(abi.encodeWithSignature("removeSolver(address)", solver));
        bool solverAllowedAfterRemoval = _isSolver(authenticator, solver);

        vm.prank(solver);
        (bool afterOk, bytes memory afterData) = SETTLEMENT.call(
            abi.encodeWithSelector(
                ICoWSettlementCrossFunction.settle.selector,
                tokens, prices, trades, interactions
            )
        );
        string memory afterReason = _decodeErrorString(afterData);
        bool rejectedBySolverGuard = !afterOk &&
            keccak256(bytes(afterReason)) == keccak256(bytes(NOT_SOLVER));

        string memory judgment;
        if (!addOk || !solverAllowedBefore || !beforePassedSolverGate ||
            !removeOk || solverAllowedAfterRemoval) {
            judgment = "inconclusive";
        } else if (rejectedBySolverGuard) {
            judgment = "rejected";
        } else {
            // Valid ABI-encoded empty arguments reach the onlySolver modifier.
            // If a removed solver passes that guard, this is a cross-function candidate.
            judgment = "supported";
        }

        string memory evidence = string.concat(
            "{\n",
            '  "chain_id": ', vm.toString(block.chainid), ",\n",
            '  "fork_block": ', vm.toString(forkBlock), ",\n",
            '  "settlement": "', vm.toString(SETTLEMENT), '",\n',
            '  "configured_authenticator": "', vm.toString(authenticator), '",\n',
            '  "configured_authenticator_implementation_slot": "', vm.toString(implementation), '",\n',
            '  "manager": "', vm.toString(manager), '",\n',
            '  "solver": "', vm.toString(solver), '",\n',
            '  "manager_add_succeeded": ', addOk ? "true" : "false", ",\n",
            '  "solver_allowed_before": ', solverAllowedBefore ? "true" : "false", ",\n",
            '  "settle_before_removal": { "outcome": "', beforeOk ? "success" : "reverted",
            '", "revert_string": "', beforeReason, '", "passed_solver_gate": ',
            beforePassedSolverGate ? "true" : "false", ', "return_or_revert_data": "', _hex(beforeData), '" },\n',
            '  "manager_remove_succeeded": ', removeOk ? "true" : "false", ",\n",
            '  "solver_allowed_after_removal": ', solverAllowedAfterRemoval ? "true" : "false", ",\n",
            '  "settle_after_removal": { "outcome": "', afterOk ? "success" : "reverted",
            '", "revert_string": "', afterReason, '", "rejected_by_not_solver_guard": ',
            rejectedBySolverGuard ? "true" : "false", ', "return_or_revert_data": "', _hex(afterData), '" },\n',
            '  "judgment": "', judgment, '"\n',
            "}\n"
        );
        vm.writeFile("cow-removed-solver-settlement-evidence.json", evidence);
    }

    function _isSolver(address authenticator, address solver) private view returns (bool value) {
        (bool ok, bytes memory data) =
            authenticator.staticcall(abi.encodeWithSignature("isSolver(address)", solver));
        require(ok && data.length >= 32, "isSolver() read failed");
        value = abi.decode(data, (bool));
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
