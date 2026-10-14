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



# Measured on the pinned DcntEth dependency chain: DcntEth -> OFTV2 -> BaseOFTV2
# -> OFTCoreV2 -> NonblockingLzApp -> LzApp -> Ownable (6 base hops).
_AUTHORITY_INHERITANCE_DEPTH_BUDGET = 6


def _contract_header(source_text: str, contract_name: str) -> tuple[str, str] | None:
    """Return a contract's inheritance header and body without resolving unrelated symbols."""
    match = re.search(
        rf"\b(?:abstract\s+)?contract\s+{re.escape(contract_name)}\b([^{{]*){{",
        source_text,
    )
    if match is None:
        return None
    return match.group(1), _source_for_contract(source_text, contract_name)


def _resolve_inherited_ownable_surface(
    source_path: str | Path,
    contract_name: str,
    *,
    depth_budget: int = _AUTHORITY_INHERITANCE_DEPTH_BUDGET,
) -> tuple[bool, str, str]:
    """Find owner() along declared contract bases; this is not a general type resolver."""
    source_file = Path(source_path).resolve()
    ancestors = list(source_file.parents)[:5]
    # Prefer the selected Foundry project root so imported base contracts under
    # lib/ remain in the bounded source search; do not stop at a crowded src/.
    search_root = next(
        (parent for parent in ancestors if (parent / "foundry.toml").is_file()),
        source_file.parent,
    )
    if search_root == source_file.parent:
        for parent in ancestors:
            try:
                if sum(1 for _ in parent.glob("*.sol")) > 1:
                    search_root = parent
                    break
            except OSError:
                continue
    source_by_contract: dict[str, str] = {}
    try:
        candidates = [p for p in search_root.rglob("*.sol") if p.is_file()]
    except OSError:
        candidates = []
    candidates.append(source_file)
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        for match in re.finditer(r"\b(?:abstract\s+)?contract\s+([A-Za-z_$][\w$]*)\b", text):
            source_by_contract.setdefault(match.group(1), text)

    current, depth = contract_name, 0
    visited: set[str] = set()
    while current and current not in visited:
        visited.add(current)
        text = source_by_contract.get(current)
        if text is None:
            return False, f"authority_inheritance_source_missing:{current}", ""
        parsed = _contract_header(text, current)
        if parsed is None:
            return False, f"authority_inheritance_declaration_missing:{current}", ""
        header, body = parsed
        if re.search(r"\bfunction\s+owner\s*\(\s*\)", body) and re.search(
            r"\bowner\s*\(\s*\)\s*(?:external|public)", body
        ):
            return True, "owner_getter_resolved", body
        bases_match = re.search(r"\bis\s+(.+)$", header, re.DOTALL)
        bases = [part.strip().split()[0] for part in bases_match.group(1).split(",") if part.strip()] if bases_match else []
        if not bases:
            return False, "no_authority_getter", ""
        if depth >= depth_budget:
            return False, f"authority_inheritance_depth_exceeded:{depth_budget}", ""
        current = next((name for name in bases if name in source_by_contract), bases[0])
        depth += 1
    return False, "authority_inheritance_cycle_detected", ""

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
    if not all((hypothesis.source_path, hypothesis.declaring_contract, hypothesis.source_line is not None)):
        raise ValueError("candidate-missing: hypothesis has no complete source identity tuple")
    identity = (str(Path(hypothesis.source_path).resolve()), hypothesis.declaring_contract, hypothesis.target_function, hypothesis.source_line)
    if str(Path(contract_model.source).resolve()) != identity[0] or contract_model.name != identity[1]:
        raise ValueError("candidate-mismatch: contract model does not match hypothesis source identity")
    matches = [item for item in contract_model.functions if item.name == identity[2] and item.line == identity[3] and str(Path(item.source or contract_model.source).resolve()) == identity[0]]
    if not matches:
        raise ValueError(f"candidate-missing: no function matches source identity {identity!r}")
    if len(matches) != 1:
        raise ValueError(f"candidate-ambiguous: {len(matches)} functions match source identity {identity!r}")
    function = matches[0]
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

    # The first supported authority surface is OpenZeppelin-style AccessControl.
    # It is only measurable when both the role getter and hasRole read are present.
    role_getter = None
    if re.search(r"\bfunction\s+hasRole\s*\(", source_text):
        role_match = re.search(
            r"\bbytes32\s+public\s+constant\s+(DEFAULT_ADMIN_ROLE)\s*=", source_text
        )
        if role_match:
            role_getter = role_match.group(1)

    ownable_supported, ownable_reason, ownable_source = _resolve_inherited_ownable_surface(
        contract_model.source, target_type
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

    # If semantic write extraction missed a simple public state assignment,
    # recover only a source-declared public scalar that the selected function assigns.
    if state_getter is None:
        for match in re.finditer(
            r"\b(address(?:\s+payable)?|bool|uint\d*|int\d*)\s+public\s+(\w+)\s*;",
            source_text,
        ):
            candidate_type, candidate_name = match.group(1).strip(), match.group(2)
            if re.search(rf"\b{re.escape(candidate_name)}\s*=", source_text):
                state_type, state_getter = candidate_type, candidate_name
                break

    # A bounded sibling comparison distinguishes privileged configuration setters from
    # permissionless state updates. The inference is recorded explicitly; it is not
    # applied to arbitrary state changes or newly-created mapping keys.
    target_is_guarded = bool(re.search(
        rf"\bfunction\s+{re.escape(function.name)}\s*\([^)]*\)[^{{;]*\bonlyOwner\b",
        source_text,
        re.DOTALL,
    ))
    guarded_configuration_sibling = any(
        match.group(1) != function.name
        for match in re.finditer(
            r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)[^{;]*\bonlyOwner\b[^{{;]*\{",
            source_text,
            re.DOTALL,
        )
    )
    authority_model_governs_state = bool(
        ownable_supported
        and state_getter
        and function.name.startswith("set")
        and not target_is_guarded
        and guarded_configuration_sibling
    )

    # Name the source state variable even when its location cannot be read at runtime.
    state_variable_name = state_getter or next(iter(function.writes), "")
    state_variable_declared = bool(
        state_variable_name
        and (
            re.search(
                rf"\bmapping\s*\([^;]*\)\s*(?:(?:public|private|internal)\s+)?{re.escape(state_variable_name)}\b",
                source_text,
            )
            or re.search(
                rf"\b(address(?:\s+payable)?|bool|uint\d*|int\d*)\s+(?:public|private|internal)\s+{re.escape(state_variable_name)}\s*;",
                source_text,
            )
        )
    )
    fresh_mapping_key = False
    if state_variable_name and not state_getter:
        fresh_key_match = re.search(
            r"\b([A-Za-z_$][\w$]*)\s*=\s*address\s*\(\s*new\s+[A-Za-z_$][\w$]*",
            source_text,
        )
        if fresh_key_match:
            fresh_key = fresh_key_match.group(1)
            fresh_mapping_key = bool(re.search(
                rf"\b{re.escape(state_variable_name)}\s*\[\s*{re.escape(fresh_key)}\s*\]\s*=",
                source_text,
            ))
    state_existence_measured = bool(state_getter or fresh_mapping_key)
    state_existed_before = bool(state_getter and state_variable_declared)
    state_measurement_available = bool(state_getter)

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

    # Record observations independently of the authority resolver's verdict branch.
    # Low-level reads let the artifact preserve whatever is measurable even when
    # source resolution fails; decode only successful, correctly-sized returns.
    observation_declarations = [
        "    address public observedCaller;",
        "    address public observedOwnerBefore;",
        "    address public observedOwnerAfter;",
        "    bool public ownerReadBeforeSucceeded;",
        "    bool public ownerReadAfterSucceeded;",
        "    string public observedStateVariable;",
        "    bool public observedStateVariableDeclared;",
        "    bool public observedStateExistedBefore;",
        "    bool public observedStateExistenceMeasured;",
        "    bool public stateMeasurementAvailable;",
        "    bool public observedAuthorityModelGovernsState;",
        "    bool public observedStateChanged;",
        "    bool public stateReadBeforeSucceeded;",
        "    bool public stateReadAfterSucceeded;",
    ]
    if state_getter:
        observation_declarations += [
            f"    {state_type} public observedStateBefore;",
            f"    {state_type} public observedStateAfter;",
        ]
    before_observation = """        observedCaller = address(attacker);
        (bool ownerBeforeOk, bytes memory ownerBeforeData) = address(target).staticcall(abi.encodeWithSignature("owner()"));
        ownerReadBeforeSucceeded = ownerBeforeOk && ownerBeforeData.length >= 32;
        if (ownerReadBeforeSucceeded) observedOwnerBefore = abi.decode(ownerBeforeData, (address));"""
    post_observation = """        (bool ownerAfterOk, bytes memory ownerAfterData) = address(target).staticcall(abi.encodeWithSignature("owner()"));
        ownerReadAfterSucceeded = ownerAfterOk && ownerAfterData.length >= 32;
        if (ownerReadAfterSucceeded) observedOwnerAfter = abi.decode(ownerAfterData, (address));"""
    if state_getter:
        before_observation += f'''
        (bool stateBeforeOk, bytes memory stateBeforeData) = address(target).staticcall(abi.encodeWithSignature("{state_getter}()"));
        stateReadBeforeSucceeded = stateBeforeOk && stateBeforeData.length >= 32;
        if (stateReadBeforeSucceeded) observedStateBefore = abi.decode(stateBeforeData, ({state_type}));'''
        post_observation += f'''
        (bool stateAfterOk, bytes memory stateAfterData) = address(target).staticcall(abi.encodeWithSignature("{state_getter}()"));
        stateReadAfterSucceeded = stateAfterOk && stateAfterData.length >= 32;
        if (stateReadAfterSucceeded) observedStateAfter = abi.decode(stateAfterData, ({state_type}));
        observedStateChanged = stateReadBeforeSucceeded && stateReadAfterSucceeded && (observedStateBefore != observedStateAfter);'''
    if role_getter:
        before_observation += "\n        bool hadRoleBefore = target.hasRole(target." + role_getter + "(), address(attacker));"
        post_observation += "\n        bool hasRoleAfter = target.hasRole(target." + role_getter + "(), address(attacker));"
        verdict_logic = f'''        if (!ok) {{
            if (hadRoleBefore != hasRoleAfter) verdict = Verdict.Inconclusive;
            else if (bytes(expectedGuard).length == 0) verdict = Verdict.Unmeasurable;
            else if (keccak256(bytes(_revertReason(returnData))) == keccak256(bytes(expectedGuard))) verdict = Verdict.Rejected;
            else verdict = Verdict.Inconclusive;
        }} else if (!hadRoleBefore && hasRoleAfter) verdict = Verdict.Supported;
        else if (hadRoleBefore == hasRoleAfter) verdict = Verdict.Rejected;
        else verdict = Verdict.Inconclusive;'''
    elif ownable_supported:
        verdict_logic = f'''        if (!ownerReadBeforeSucceeded || !ownerReadAfterSucceeded) {{
            verdict = Verdict.Unmeasurable;
            verdictReason = "owner_measurement_unavailable";
        }} else if (observedOwnerBefore == address(attacker)) {{
            verdict = Verdict.Rejected;
            verdictReason = "caller_authorized";
        }} else if (!ok) {{
            if ({str(target_is_guarded).lower()}) {{
                verdict = Verdict.Rejected;
                verdictReason = "guarded_function_reverted";
            }} else if (observedOwnerBefore != observedOwnerAfter) {{
                verdict = Verdict.Inconclusive;
                verdictReason = "authority_changed_during_reverted_call";
            }} else if (bytes(expectedGuard).length != 0 && keccak256(bytes(_revertReason(returnData))) == keccak256(bytes(expectedGuard))) {{
                verdict = Verdict.Rejected;
                verdictReason = "unauthorized_call_reverted";
            }} else {{
                verdict = Verdict.Inconclusive;
                verdictReason = "revert_reason_not_discriminating";
            }}
        }} else if (!stateReadBeforeSucceeded || !stateReadAfterSucceeded) {{
            verdict = Verdict.Unmeasurable;
            verdictReason = "protected_state_measurement_unavailable";
        }} else if (!observedStateExistedBefore) {{
            verdict = Verdict.Unmeasurable;
            verdictReason = "state_not_preexisting";
        }} else if (!observedAuthorityModelGovernsState) {{
            verdict = Verdict.Rejected;
            verdictReason = "authority_model_not_derived_for_state";
        }} else if (observedStateChanged) {{
            verdict = Verdict.Supported;
            verdictReason = "unauthorized_preexisting_authority_governed_state_changed";
        }} else {{
            verdict = Verdict.Rejected;
            verdictReason = "protected_state_unchanged";
        }}'''
    else:
        verdict_logic = f'        verdict = Verdict.Unmeasurable; verdictReason = "{ownable_reason}";'

    observation_logging = ""
    if state_getter:
        if state_type == "bool":
            state_log_type, state_before_value, state_after_value = "bool", "observedStateBefore", "observedStateAfter"
        elif state_type.startswith(("uint", "int")):
            state_log_type, state_before_value, state_after_value = "uint256", "uint256(observedStateBefore)", "uint256(observedStateAfter)"
        else:
            state_log_type, state_before_value, state_after_value = "address", "observedStateBefore", "observedStateAfter"
        observation_logging = (
            f'        (bool stateBeforeLogged,) = consoleAddress.staticcall(abi.encodeWithSignature("log(string,{state_log_type})", "CYDRA_OBS_STATE_BEFORE", {state_before_value}));\n'
            f'        stateBeforeLogged;\n'
            f'        (bool stateAfterLogged,) = consoleAddress.staticcall(abi.encodeWithSignature("log(string,{state_log_type})", "CYDRA_OBS_STATE_AFTER", {state_after_value}));\n'
            f'        stateAfterLogged;'
        )

    observation_declarations = "\n".join(observation_declarations)

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
    bool public observedCallSucceeded;
    string internal expectedGuard = {guard_literal};
    string public verdictReason;
{observation_declarations}

    function _targetCreationCode() internal pure returns (bytes memory) {{
        return type({target_type}).creationCode;
    }}

    function _recordStateMetadata(address consoleAddress) internal {{
        (bool stateNameLogged,) = consoleAddress.staticcall(abi.encodeWithSignature("log(string,string)", "CYDRA_OBS_STATE_VARIABLE", observedStateVariable));
        stateNameLogged;
        (bool stateDeclaredLogged,) = consoleAddress.staticcall(abi.encodeWithSignature("log(string,bool)", "CYDRA_OBS_STATE_VARIABLE_DECLARED", observedStateVariableDeclared));
        stateDeclaredLogged;
        (bool stateExistsLogged,) = consoleAddress.staticcall(abi.encodeWithSignature("log(string,bool)", "CYDRA_OBS_STATE_EXISTED_BEFORE", observedStateExistedBefore));
        stateExistsLogged;
        (bool stateExistenceMeasuredLogged,) = consoleAddress.staticcall(abi.encodeWithSignature("log(string,bool)", "CYDRA_OBS_STATE_EXISTENCE_MEASURED", observedStateExistenceMeasured));
        stateExistenceMeasuredLogged;
        (bool stateMeasurementAvailableLogged,) = consoleAddress.staticcall(abi.encodeWithSignature("log(string,bool)", "CYDRA_OBS_STATE_MEASUREMENT_AVAILABLE", stateMeasurementAvailable));
        stateMeasurementAvailableLogged;
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
        (bool callerLogged,) = consoleAddress.staticcall(abi.encodeWithSignature("log(string,address)", "CYDRA_OBS_CALLER", observedCaller));
        callerLogged;
        (bool callSucceededLogged,) = consoleAddress.staticcall(abi.encodeWithSignature("log(string,bool)", "CYDRA_OBS_CALL_SUCCEEDED", observedCallSucceeded));
        callSucceededLogged;
        (bool ownerBeforeLogged,) = consoleAddress.staticcall(abi.encodeWithSignature("log(string,address)", "CYDRA_OBS_OWNER_BEFORE", observedOwnerBefore));
        ownerBeforeLogged;
        (bool ownerAfterLogged,) = consoleAddress.staticcall(abi.encodeWithSignature("log(string,address)", "CYDRA_OBS_OWNER_AFTER", observedOwnerAfter));
        ownerAfterLogged;
        (bool ownerBeforeOkLogged,) = consoleAddress.staticcall(abi.encodeWithSignature("log(string,bool)", "CYDRA_OBS_OWNER_BEFORE_READ_OK", ownerReadBeforeSucceeded));
        ownerBeforeOkLogged;
        (bool ownerAfterOkLogged,) = consoleAddress.staticcall(abi.encodeWithSignature("log(string,bool)", "CYDRA_OBS_OWNER_AFTER_READ_OK", ownerReadAfterSucceeded));
        ownerAfterOkLogged;
        _recordStateMetadata(consoleAddress);
        (bool stateGovernedLogged,) = consoleAddress.staticcall(abi.encodeWithSignature("log(string,bool)", "CYDRA_OBS_AUTHORITY_MODEL_GOVERNS_STATE", observedAuthorityModelGovernsState));
        stateGovernedLogged;
        (bool stateChangedLogged,) = consoleAddress.staticcall(abi.encodeWithSignature("log(string,bool)", "CYDRA_OBS_STATE_CHANGED", observedStateChanged));
        stateChangedLogged;
{observation_logging}
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
        observedStateVariable = "{state_variable_name}";
        observedStateVariableDeclared = {str(state_variable_declared).lower()};
        observedStateExistedBefore = {str(state_existed_before).lower()};
        observedStateExistenceMeasured = {str(state_existence_measured).lower()};
        stateMeasurementAvailable = {str(state_measurement_available).lower()};
        observedAuthorityModelGovernsState = {str(authority_model_governs_state).lower()};
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
        observedCallSucceeded = ok;
{post_observation}
{verdict_logic}
        if (verdict == Verdict.Inconclusive && bytes(verdictReason).length == 0) verdictReason = "runtime_outcome_not_discriminating";
        if (verdict == Verdict.Rejected && bytes(verdictReason).length == 0) verdictReason = "authority_membership_or_state_control_not_violated";
        if (verdict == Verdict.Supported && bytes(verdictReason).length == 0) verdictReason = "authority_membership_gained";
        assert(verdict != Verdict.None);
        _recordVerdict();
    }}
}}
'''
    path.write_text(source, encoding="utf-8")
    return path