verdict_logic = '        verdict = Verdict.Unmeasurable; verdictReason = "{ownable_reason}";'

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pragma = contract_model.pragma or "^0.8.20"
    encoded_arguments = f", {arguments}" if arguments else ""
    source = f'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Experiment: {experiment.experiment_id}
import {{ {target_type} }} from "{target_import}";

contract CydraUnauthorizedCaller {{
    function execute(address target, bytes calldata payload) external returns (bool, bytes memory) {{
        return target.call(payload);
    }}
}}

contract CydraBlindAuthorizationTest {{
    enum Verdict {{ None, Supported, Rejected, Inconclusive, Unmeasurable }}
    {target_type} internal target;
    CydraUnauthorizedCaller internal attacker;
    Verdict public verdict;
    bool public deployed;
    string internal expectedGuard = {guard_literal};
    string public verdictReason;

    function _targetCreationCode() internal pure returns (bytes memory) {{
        return type({target_type}).creationCode;
    }}

    function _recordVerdict() internal {{
        address consoleAddress = address(uint160(0x00000000000000000000636f6e736f6c652e6c6f67));
        (bool logged,) = consoleAddress.staticcall(
            abi.encodeWithSignature("log(string,uint256)", "CYDRA_VERDICT", uint256(verdict))
        );
        logged;
        (bool reasonLogged,) = consoleAddress.staticcall(
            abi.encodeWithSignature("log(string,string)", "CYDRA_VERDICT_REASON", verdictReason)
        );
        reasonLogged;
    }}

    function _revertReason(bytes memory data) internal pure returns (string memory) {{
        if (data.length < 68) return "";
        bytes4 selector;
        assembly {{ selector := mload(add(data, 0x20)) }}
        if (selector != 0x08c379a0) return "";
        assembly {{ data := add(data, 0x04) }}
        return abi.decode(data, (string));
    }}

    function setUp() public {{
        bytes memory initCode = abi.encodePacked(_targetCreationCode(), {constructor_suffix});
        address deployedAddress;
        assembly {{ deployedAddress := create(0, add(initCode, 0x20), mload(initCode)) }}
        if (deployedAddress == address(0)) {{
            verdict = Verdict.Inconclusive;
            deployed = false;
            return;
        }}
        target = {target_type}(payable(deployedAddress));
        attacker = new CydraUnauthorizedCaller();
        deployed = true;
    }}

    function testUnauthorizedCallerCapabilityDelta() public {{
        if (!deployed) {{
            assert(verdict == Verdict.Inconclusive);
            _recordVerdict();
            return;
        }}
{before_observation}
        (bool ok, bytes memory returnData) = attacker.execute(
            address(target),
            abi.encodeWithSignature(
                "{function.name}({','.join(parameter.type.split()[0] for parameter in function.parameters)})"{encoded_arguments}
            )
        );
{post_observation}
{verdict_logic}
        if (verdict == Verdict.Inconclusive && bytes(verdictReason).length == 0) verdictReason = "runtime_outcome_not_discriminating";
        assert(verdict != Verdict.None);
        _recordVerdict();
    }}
}}
'''
    path.write_text(source, encoding="utf-8")
    return path
