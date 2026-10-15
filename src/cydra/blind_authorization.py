from __future__ import annotations

from pathlib import Path
import re

from .models import ContractModel, Experiment, Hypothesis
from .planned_call import render_function_call


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


def _source_for_contract(source_text: str, contract_name: str) -> str:
    """Limit regex-based capability and guard extraction to the named contract body."""
    match = re.search(
        rf"\b(?:abstract\s+)?contract\s+{re.escape(contract_name)}\b[^{{]*{{",
        source_text,
    )
    if match is None:
        return source_text
    start = match.start()
    depth = 0
    for index in range(match.end() - 1, len(source_text)):
        char = source_text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source_text[start:index + 1]
    return source_text[start:]


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

    source_text = _source_for_contract(source_text, target_type)

    # OpenZeppelin AccessControl authority is measured using the exact role
    # expression carried by the target's onlyRole(...) modifier invocation.
    # The identifier is read through the deployed contract's public constant
    # getter, so keccak256 role values are never reconstructed from their names.
    role_getter = None
    role_invocation = next(
        (
            arguments
            for modifier_name, arguments in function.modifier_arguments
            if modifier_name.lower() == "onlyrole" and len(arguments) == 1
        ),
        None,
    )
    if role_invocation:
        role_expression = role_invocation[0].strip()
        role_identifier = (
            role_expression
            if re.fullmatch(r"[A-Za-z_]\\w*", role_expression)
            else None
        )
        role_constant_declared = bool(
            role_identifier
            and re.search(
                rf"\\bbytes32\\s+public\\s+constant\\s+{re.escape(role_identifier)}\\s*=",
                source_text,
            )
        )
        inherited_access_control = any(
            "AccessControlUpgradeable" in inherited
            or inherited == "AccessControl"
            for inherited in contract_model.inherits
        )
        inherited_default_admin = (
            role_identifier == "DEFAULT_ADMIN_ROLE" and inherited_access_control
        )
        inherited_has_role = any(
            item.name == "hasRole" for item in contract_model.inherited_functions
        )
        has_role_surface = bool(
            re.search(r"\\bfunction\\s+hasRole\\s*\\(", source_text)
            or inherited_has_role
            or inherited_access_control
        )
        if role_identifier and has_role_surface and (
            role_constant_declared or inherited_default_admin
        ):
            role_getter = role_identifier

    ownable_supported = bool(
        re.search(r"\bfunction\s+owner\s*\(\s*\)", source_text)
        and re.search(r"\bowner\s*\(\s*\)\s*(?:external|public)", source_text)
    )

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

    # Only a single source-grounded revert string is accepted as a guard oracle.
    guard_strings = set(re.findall(
        r"(?:require|revert)\s*\([^;]*?[\"']([^\"']{3,})[\"']",
        source_text,
        re.DOTALL,
    ))
    expected_guard = next(iter(guard_strings)) if len(guard_strings) == 1 else None
    guard_literal = (
        '"' + expected_guard.replace("\\", "\\\\").replace('"', '\\"') + '"'
        if expected_guard else '""'
    )

    if role_getter:
        before_observation = (
            f"        bool hadRoleBefore = target.hasRole(target.{role_getter}(), address(attacker));"
        )
        post_observation = (
            f"        bool hasRoleAfter = target.hasRole(target.{role_getter}(), address(attacker));"
        )
        verdict_logic = f'''        if (!ok) {{
            if (hadRoleBefore != hasRoleAfter) verdict = Verdict.Inconclusive;
            else if (_isAccessControlUnauthorized(returnData)) verdict = Verdict.Rejected;
            else if (bytes(expectedGuard).length > 0 && keccak256(bytes(_revertReason(returnData))) == keccak256(bytes(expectedGuard))) verdict = Verdict.Rejected;
            else verdict = Verdict.Inconclusive;
        }} else if (!hadRoleBefore) verdict = Verdict.Supported;
        else verdict = Verdict.Inconclusive;'''
    elif ownable_supported:
        before_observation = "        address ownerBefore = target.owner();"
        post_observation = "        address ownerAfter = target.owner();"
        verdict_logic = f'''        if (!ok) {{
            if (ownerBefore != ownerAfter) verdict = Verdict.Inconclusive;
            else if (expectedGuard.length == 0) verdict = Verdict.Unmeasurable;
            else if (keccak256(bytes(_revertReason(returnData))) == keccak256(bytes(expectedGuard))) verdict = Verdict.Rejected;
            else verdict = Verdict.Inconclusive;
        }} else if (ownerBefore != address(attacker) && ownerAfter == address(attacker)) verdict = Verdict.Supported;
        else if (ownerBefore == ownerAfter) verdict = Verdict.Rejected;
        else verdict = Verdict.Inconclusive;'''
    else:
        # A public state getter is not itself proof of an authority relationship.
        before_observation = ""
        post_observation = ""
        verdict_logic = '        verdict = Verdict.Unmeasurable; verdictReason = "no_authority_getter";'

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

    function _isAccessControlUnauthorized(bytes memory data) internal pure returns (bool) {{
        if (data.length < 4) return false;
        bytes4 selector;
        assembly {{ selector := mload(add(data, 0x20)) }}
        return selector == bytes4(keccak256("AccessControlUnauthorizedAccount(address,bytes32)"));
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
