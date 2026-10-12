from __future__ import annotations

from pathlib import Path
import re

from .models import ContractModel, Experiment, Hypothesis
from .planned_call import render_function_call
from .authorization_runtime import security_assertion_marker


def _constructor_argument(parameter, *, abi_only: bool = False) -> str:
    """Return a compiler-valid constructor value, or fail closed if the model is incomplete."""
    parameter_type = str(parameter.type or "").strip()
    if not parameter_type:
        raise ValueError(
            f"constructor parameter {parameter.name or '<unnamed>'} has no resolved Solidity type"
        )
    base = parameter_type.split()[0].rstrip("[]")
    if parameter_type.endswith("[]"):
        return f"new {base}[](0)"
    if parameter_type == "address payable":
        return "payable(address(0x1001))"
    if base == "address":
        return "address(0x1001)"
    if base == "bool":
        return "false"
    if base.startswith(("uint", "int")):
        return "0"
    if base == "string":
        return '""'
    if base == "bytes":
        return 'bytes("")'
    if base.startswith("bytes") and base[5:].isdigit():
        return "bytes32(uint256(1))" if base == "bytes32" else f"{base}(0)"
    return "address(0x1001)"


def _constructor_arguments(contract_model: ContractModel, *, abi_only: bool = False) -> str:
    constructor = contract_model.constructor
    if constructor is None:
        return ""
    arguments = []
    for parameter in constructor.parameters:
        rendered = _constructor_argument(parameter, abi_only=abi_only)
        if rendered is None:
            raise ValueError(
                f"constructor parameter {parameter.name or '<unnamed>'} could not be rendered"
            )
        arguments.append(rendered)
    return ", ".join(arguments)


def generate_blind_authorization_test_from_experiment(
    hypothesis: Hypothesis,
    experiment: Experiment,
    target_import: str,
    target_type: str,
    output_path: str | Path,
    contract_model: ContractModel,
    creation_bytecode: str | None = None,
) -> Path:
    """Render an authorization test with explicit capability-measurement verdicts."""
    if hypothesis.invariant_id != "INV-AUTH-001":
        raise ValueError(
            f"Unsupported invariant for blind authorization generation: {hypothesis.invariant_id}"
        )
    if experiment.hypothesis_id != hypothesis.hypothesis_id:
        raise ValueError(
            f"experiment/hypothesis mismatch: {experiment.hypothesis_id} != {hypothesis.hypothesis_id}"
        )
    function = next(
        (item for item in contract_model.functions if item.name == hypothesis.target_function),
        None,
    )
    if function is None:
        raise ValueError(f"Model has no target function: {hypothesis.target_function}")
    if function.visibility not in {"public", "external"}:
        raise ValueError(f"authorization target {function.name} is not externally callable")

    call = render_function_call(experiment, function)
    arguments = call.removeprefix(f"target.{function.name}(").removesuffix(");")
    constructor_arguments = _constructor_arguments(
        contract_model, abi_only=creation_bytecode is not None
    )
    constructor_suffix = (
        f"abi.encode({constructor_arguments})" if constructor_arguments else 'bytes("")'
    )

    try:
        source_text = Path(contract_model.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        source_text = ""

    # The first supported authority surface is OpenZeppelin-style AccessControl.
    # It is only measurable when both the role getter and hasRole read are present.
    role_getter = None
    if re.search(r"\bfunction\s+hasRole\s*\(", source_text):
        role_match = re.search(
            r"\bbytes32\s+public\s+constant\s+(DEFAULT_ADMIN_ROLE)\s*=", source_text
        )
        if role_match:
            role_getter = role_match.group(1)

    state_getter = None
    state_type = None
    for written in function.writes:
        match = re.search(
            rf"\b(address(?:\s+payable)?|bool|uint\d*|int\d*)\s+public\s+{re.escape(written)}\s*;",
            source_text,
        )
        if match:
            state_type = match.group(1).strip()
            state_getter = written
            break

    if role_getter:
        before_observation = (
            f"        bool hadRoleBefore = target.hasRole(target.{role_getter}(), address(attacker));"
        )
        post_observation = (
            f"        bool hasRoleAfter = target.hasRole(target.{role_getter}(), address(attacker));"
        )
        verdict_logic = f'''        if (!hadRoleBefore && hasRoleAfter) {{
            emit CydraVerdict("supported");
            require(false, "{security_assertion_marker()}: unauthorized caller gained DEFAULT_ADMIN_ROLE");
        }}
        if (hadRoleBefore == hasRoleAfter) emit CydraVerdict("rejected");
        else emit CydraVerdict("unmeasurable");'''
    elif state_getter is not None:
        before_observation = f"        {state_type} beforeState = target.{state_getter}();"
        post_observation = f"        {state_type} afterState = target.{state_getter}();"
        verdict_logic = f'''        require(ok, "CYDRA: call execution was inconclusive because it reverted");
        if (afterState == beforeState) emit CydraVerdict("rejected");
        else emit CydraVerdict("unmeasurable");'''
    else:
        before_observation = ""
        post_observation = ""
        verdict_logic = '''        // No supported authority read: success/failure cannot establish an authority delta.
        emit CydraVerdict("unmeasurable");'''

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pragma = contract_model.pragma or "^0.8.20"
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
    {target_type} internal target;
    CydraUnauthorizedCaller internal attacker;

    event CydraVerdict(string verdict);

    function _targetCreationCode() internal pure returns (bytes memory) {{
        return type({target_type}).creationCode;
    }}

    function setUp() public {{
        bytes memory initCode = abi.encodePacked(_targetCreationCode(), {constructor_suffix});
        address deployed;
        assembly {{ deployed := create(0, add(initCode, 0x20), mload(initCode)) }}
        require(deployed != address(0), "CYDRA: constructor deployment failed");
        target = {target_type}(payable(deployed));
        attacker = new CydraUnauthorizedCaller();
    }}

    function testUnauthorizedCallerCapabilityDelta() public {{
{before_observation}
        (bool ok,) = attacker.execute(
            address(target),
            abi.encodeWithSignature(
                "{function.name}({','.join(parameter.type.split()[0] for parameter in function.parameters)})",
                {arguments}
            )
        );
{post_observation}
        if (!ok) {{
            emit CydraVerdict("inconclusive");
            return;
        }}
{verdict_logic}
    }}
}}
'''
    path.write_text(source, encoding="utf-8")
    return path
