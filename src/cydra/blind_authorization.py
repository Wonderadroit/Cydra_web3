from __future__ import annotations

from pathlib import Path
import re

from .models import ContractModel, Experiment, Hypothesis
from .planned_call import render_function_arguments
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
    # ABI encoding accepts an address for interface/contract constructor
    # parameters, avoiding extra source imports in historical harnesses.
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
    """Render a one-sided authorization invariant test from the canonical plan."""
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

    arguments = render_function_arguments(experiment, function)
    constructor_arguments = _constructor_arguments(
        contract_model, abi_only=creation_bytecode is not None
    )
    constructor_encoding = (
        f"abi.encode({constructor_arguments})"
        if constructor_arguments
        else 'bytes("")'
    )
    # Prefer typed deployment for blind authorization harnesses. A raw
    # creation-bytecode path can cause Foundry to synthesize constructor-argument
    # helper structs whose ABI shape is lost for multi-parameter constructors.
    # The target import is already part of the authorized harness boundary, so
    # direct deployment preserves the constructor ABI exactly.
    init_expression = ""
    target_declaration = f"{target_type} internal target;"
    import_line = f'import {{ {target_type} }} from "{target_import}";'
    target_cast = target_type

    pragma = contract_model.pragma or "^0.8.20"
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    state_getter = None
    state_type = None
    try:
        source_text = Path(contract_model.source).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        source_text = ""

    # A verdict is measurable only when the generated harness can observe a
    # state variable written by the target operation.
    for written in function.writes:
        match = re.search(
            rf"\\b(address(?:\\s+payable)?|bool|uint\\d*|int\\d*)\\s+public\\s+{re.escape(written)}\\s*;",
            source_text,
        )
        if match:
            state_type = match.group(1).strip()
            state_getter = written
            break
    if state_getter is None:
        raise ValueError(
            "no matching public scalar getter for modeled writes; authorization differential is unmeasurable"
        )

    # Resolve the authorized actor only from a recognized modifier guard in the
    # target source. Do not guess owner/admin identity from names alone.
    modifier_bodies = {
        match.group(1): match.group(2)
        for match in re.finditer(
            r"\\bmodifier\\s+([A-Za-z_]\\w*)\\s*\\([^)]*\\)\\s*\\{([^{}]*)\\}",
            source_text,
            re.DOTALL,
        )
    }
    principal = None
    for modifier in function.modifiers:
        body = modifier_bodies.get(modifier)
        if body is None:
            continue
        guard = re.search(
            r"\\bmsg\\s*\\.\\s*sender\\s*==\\s*([A-Za-z_]\\w*)|"
            r"\\b([A-Za-z_]\\w*)\\s*==\\s*msg\\s*\\.\\s*sender\\b",
            body,
        )
        if guard:
            candidate = guard.group(1) or guard.group(2)
            if re.search(
                rf"\\baddress(?:\\s+payable)?\\s+public\\s+{re.escape(candidate)}\\s*;",
                source_text,
            ):
                principal = candidate
                break
    if principal is None:
        raise ValueError(
            "could not derive an authorized caller from a recognized modifier and public address getter"
        )

    # Use a valid, state-changing argument vector for both callers. The attacker
    # is tested first; the authorized control then uses the exact same calldata.
    # If no argument can be varied consistently with the observed state type, fail
    # closed instead of claiming an authorization verdict.
    mutable_value = None
    state_base = state_type.split()[0]
    for index, parameter in enumerate(function.parameters):
        parameter_base = parameter.type.split()[0]
        if parameter_base != state_base:
            continue
        if state_base == "address":
            mutable_value = (
                f"address nextValue = address(0xBEEF);\\n"
                f"        if (nextValue == target.{state_getter}()) nextValue = address(0xF00D);"
            )
        elif state_base == "address" and state_type == "address payable":
            mutable_value = (
                f"address payable nextValue = payable(address(0xBEEF));\\n"
                f"        if (nextValue == target.{state_getter}()) nextValue = payable(address(0xF00D));"
            )
        elif state_base == "bool":
            mutable_value = f"bool nextValue = !target.{state_getter}();"
        elif state_base.startswith(("uint", "int")):
            mutable_value = (
                f"{state_base} nextValue = target.{state_getter}() == 0 ? 1 : 0;"
            )
        if mutable_value is not None:
            arguments = tuple(
                "nextValue" if position == index else argument
                for position, argument in enumerate(arguments)
            )
            break
    if mutable_value is None:
        raise ValueError(
            "no supported input can be tied to the observed state getter; authorization differential is unmeasurable"
        )

    parameter_types = ",".join(parameter.type.split()[0] for parameter in function.parameters)
    argument_list = ", ".join(arguments)
    state_snapshot = f"{state_type} beforeState = target.{state_getter}();"
    state_after = f"target.{state_getter}()"
    source = f\'''// SPDX-License-Identifier: UNLICENSED
pragma solidity {pragma};
// Hypothesis: {hypothesis.hypothesis_id}
// Experiment: {experiment.experiment_id}
// Differential control: unauthorized caller first, authorized caller second, identical calldata.
import {{ {target_type} }} from "{target_import}";

interface Vm {{
    function prank(address msgSender) external;
}}

contract CydraBlindAuthorizationTest {{
    Vm private constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    {target_type} internal target;

    function _targetCreationCode() internal pure returns (bytes memory) {{
        return type({target_type}).creationCode;
    }}

    function setUp() public {{
        bytes memory initCode = abi.encodePacked(
            _targetCreationCode(),
            {constructor_suffix}
        );
        address deployed;
        assembly {{
            deployed := create(0, add(initCode, 0x20), mload(initCode))
        }}
        require(deployed != address(0), "CYDRA: constructor deployment failed");
        target = {target_type}(payable(deployed));
    }}

    function testAuthorizationDifferentialOnModeledState() public {{
        address authorized = target.{principal}();
        require(authorized != address(0), "CYDRA_MEASUREMENT_ASSERTION: authorized principal unavailable");
        address unauthorized = address(0xCAFE);
        if (unauthorized == authorized) unauthorized = address(0xCAFD);
        {state_snapshot}
        {mutable_value}
        bytes memory payload = abi.encodeWithSignature(
            "{function.name}({parameter_types})",
            {argument_list}
        );

        vm.prank(unauthorized);
        (bool unauthorizedOk,) = address(target).call(payload);
        if (unauthorizedOk && {state_after} != beforeState) {{
            require(false, "{security_assertion_marker()}: unauthorized caller mutated modeled administrative state");
        }}
        require(
            !unauthorizedOk && {state_after} == beforeState,
            "CYDRA_MEASUREMENT_ASSERTION: unauthorized differential control was not established"
        );

        vm.prank(authorized);
        (bool authorizedOk,) = address(target).call(payload);
        require(authorizedOk, "CYDRA_MEASUREMENT_ASSERTION: authorized control failed");
        require(
            {state_after} != beforeState,
            "CYDRA_MEASUREMENT_ASSERTION: authorized control did not change observed state"
        );
    }}
}}
\'''
    path.write_text(source, encoding="utf-8")
    return path
