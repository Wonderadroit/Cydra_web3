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



def _source_closure_text(source_path: str | Path) -> str:
    """Read the target and its local Solidity import closure for inherited view readers."""
    root = Path(source_path).resolve()
    pending = [root]
    seen: set[Path] = set()
    chunks: list[str] = []
    import_re = re.compile(r'''\bimport\s+(?:[^"']+\s+from\s+)?["']([^"']+)["']\s*;''')
    while pending:
        current = pending.pop()
        if current in seen or not current.is_file() or current.suffix != ".sol":
            continue
        seen.add(current)
        try:
            text = current.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        chunks.append(text)
        for imported in import_re.findall(text):
            if imported.startswith("."):
                candidate = (current.parent / imported).resolve()
                if candidate not in seen:
                    pending.append(candidate)
    return "\n".join(chunks)


def _function_body_for_name(source_text: str, name: str) -> str | None:
    for match in re.finditer(
        r"\bfunction\s+" + re.escape(name) + r"\s*\([^)]*\)[^{;]*\{",
        source_text,
        re.DOTALL,
    ):
        depth = 1
        end = match.end()
        while end < len(source_text) and depth:
            if source_text[end] == "{":
                depth += 1
            elif source_text[end] == "}":
                depth -= 1
            end += 1
        if depth == 0:
            return source_text[match.end():end - 1]
    return None


def _parameter_names_and_types(signature: str) -> list[tuple[str, str]]:
    parameters = []
    for item in signature.split(","):
        words = re.sub(r"\b(memory|calldata|storage|payable)\b", "", item).strip().split()
        if len(words) >= 2:
            parameters.append((words[-1], words[0]))
    return parameters


def _resolve_state_observer(
    source_text: str, function: FunctionModel, written: str
) -> tuple[str, str, tuple[int, ...]] | None:
    """Resolve a state observation to a real view call and target-argument bindings.

    The returned tuple is (callable name, return type, target parameter indexes).
    Auto-generated public mapping getters use the mapping's declared key order.
    Explicit view readers use their declared signature order and name-bound args.
    """
    # Public scalar or mapping auto-getter. For mappings, extract keys from the
    # declaration in order; do not reuse target-function parameter order blindly.
    declaration = re.search(
        r"\\bmapping\\s*\\(\\s*([A-Za-z_]\\w*)\\s*(?:([A-Za-z_]\\w*))?\\s*=>\\s*"
        r"mapping\\s*\\(\\s*([A-Za-z_]\\w*)\\s*(?:([A-Za-z_]\\w*))?\\s*=>\\s*"
        r"([A-Za-z_]\\w*)\\s*(?:([A-Za-z_]\\w*))?\\s*\\)\\s*\\)\\s*public\\s+"
        + re.escape(written) + r"\\b",
        source_text,
    )
    scalar = re.search(
        r"\b(address(?:\s+payable)?|bool|uint\d*|int\d*|bytes\d*)\s+public\s+"
        + re.escape(written) + r"\s*;",
        source_text,
    )
    target_params = [(p.name, p.type.split()[0]) for p in function.parameters]

    def indexes_for_names(names: list[str]) -> tuple[int, ...] | None:
        indexes = []
        for name in names:
            matches = [i for i, (param_name, _) in enumerate(target_params) if param_name == name]
            if len(matches) != 1:
                return None
            indexes.append(matches[0])
        return tuple(indexes)

    if scalar:
        return written, scalar.group(1).strip(), ()

    if declaration:
        key_specs = [
            (declaration.group(1), declaration.group(2)),
            (declaration.group(3), declaration.group(4)),
        ]
        indexes = []
        for key_type, key_name in key_specs:
            named = [i for i, (param_name, _) in enumerate(target_params) if key_name and param_name == key_name]
            typed = [i for i, (_, param_type) in enumerate(target_params) if param_type == key_type]
            choices = named if len(named) == 1 else typed if len(typed) == 1 else []
            if not choices:
                indexes = []
                break
            indexes.append(choices[0])
        if len(indexes) == len(key_specs):
            return written, declaration.group(5).strip(), tuple(indexes)

    # Prefer an explicit public/external view function whose body reads the
    # exact state target and whose argument names can be bound to target inputs.
    function_pattern = re.compile(
        r"\bfunction\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*"
        r"((?:(?:public|external|internal|private|view|pure|virtual|override|returns|payable|"
        r"memory|calldata|storage|\w+)\s*)*)\s*returns\s*\(\s*"
        r"(address(?:\s+payable)?|bool|uint\d*|int\d*|bytes\d*)[^)]*\)\s*\{",
        re.DOTALL,
    )
    explicit = []
    for match in function_pattern.finditer(source_text):
        name, params, qualifiers, return_type = match.group(1), match.group(2), match.group(3), match.group(4)
        if not re.search(r"\b(public|external)\b", qualifiers) or not re.search(r"\bview\b", qualifiers):
            continue
        body = _function_body_for_name(source_text, name)
        if body is None or not re.search(r"\b" + re.escape(written) + r"\b", body):
            continue
        parsed = _parameter_names_and_types(params)
        indexes = indexes_for_names([name for name, _ in parsed])
        if indexes is not None:
            explicit.append((name, return_type.strip(), indexes))
    if explicit:
        # Prefer conventional getter names, then the shortest unambiguous match.
        def priority(item):
            name = item[0]
            normalized = written.lstrip("_")
            conventional = name.lower() in {
                "get" + normalized.lower(), "is" + normalized.lower(),
                normalized.lower(), "get" + normalized.lstrip("_").lower(),
            }
            return (0 if conventional else 1, len(name), name)
        return sorted(explicit, key=priority)[0]

    # One-hop reader explicitly called from the target body, e.g.
    # addValidator -> isValidator(virtualId, validator).
    target_body = _function_body_for_name(source_text, function.name)
    if target_body:
        for call in re.finditer(r"\b([A-Za-z_]\w*)\s*\(([^()]*)\)", target_body):
            name, args = call.group(1), call.group(2)
            body = _function_body_for_name(source_text, name)
            if body is None or not re.search(r"\b" + re.escape(written) + r"\b", body):
                continue
            arg_names = [part.strip() for part in args.split(",") if part.strip()]
            indexes = indexes_for_names(arg_names)
            if indexes is None:
                continue
            signature = re.search(
                r"\bfunction\s+" + re.escape(name) + r"\s*\([^)]*\)[^{;]*returns\s*\(\s*"
                r"(address(?:\s+payable)?|bool|uint\d*|int\d*|bytes\d*)",
                source_text,
                re.DOTALL,
            )
            if signature:
                return name, signature.group(1).strip(), indexes

    # Last-resort name-pattern match, still requiring a real body read and a
    # name/type-compatible signature. No guessed storage or synthetic getter.
    normalized = written.lstrip("_")
    patterns = {("is" + normalized).lower(), ("get" + normalized).lower()}
    for name, return_type, indexes in explicit:
        if name.lower() in patterns:
            return name, return_type, indexes
    return None


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
    observer_indexes: tuple[int, ...] = ()
    try:
        source_text = _source_closure_text(contract_model.source)
    except (OSError, UnicodeError):
        source_text = ""

    # Ordered lookup: global getter/signature; a one-hop view reader called by
    # the target body; finally conventional isX/getX naming. Each candidate
    # must read the modeled state target and bind its arguments to target inputs.
    for written in function.writes:
        observer = _resolve_state_observer(source_text, function, written)
        if observer is not None:
            state_getter, state_type, observer_indexes = observer
            break
    if state_getter is None:
        first_missing = function.writes[0] if function.writes else "<no-modeled-write>"
        raise ValueError(
            f"no_matching_getter:{first_missing}; authorization differential is unmeasurable"
        )

    # Resolve the authorized actor only from a recognized modifier guard in the
    # target source. Do not guess owner/admin identity from names alone.
    modifier_bodies = {
        match.group(1): match.group(2)
        for match in re.finditer(
            r"\bmodifier\s+([A-Za-z_]\w*)\s*\([^)]*\)\s*\{([^{}]*)\}",
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
            r"\bmsg\s*\.\s*sender\s*==\s*([A-Za-z_]\w*)|"
            r"\b([A-Za-z_]\w*)\s*==\s*msg\s*\.\s*sender\b",
            body,
        )
        if guard:
            candidate = guard.group(1) or guard.group(2)
            if re.search(
                rf"\baddress(?:\s+payable)?\s+public\s+{re.escape(candidate)}\s*;",
                source_text,
            ):
                principal = candidate
                break
    # Use a valid, state-changing argument vector for both callers. The attacker
    # is tested first; the authorized control then uses the exact same calldata.
    # If no argument can be varied consistently with the observed state type, fail
    # closed instead of claiming an authorization verdict.
    mutable_value = None
    # Mutate a target argument that actually feeds the observer. For mapping
    # readers this keeps the pre/post reads on the same key selected for calldata.
    candidate_indexes = list(observer_indexes)
    if not candidate_indexes:
        candidate_indexes = [
            i for i, parameter in enumerate(function.parameters)
            if parameter.type.split()[0] == state_type.split()[0]
        ]
    candidate_indexes.sort(key=lambda i: (0 if function.parameters[i].type.split()[0] == "address" else 1, i))
    for index in candidate_indexes:
        parameter_base = function.parameters[index].type.split()[0]
        current = arguments[index]
        if parameter_base == "address":
            mutable_value = (
                f"address nextValue = address(0xBEEF);\n"
                f"        if (nextValue == {current}) nextValue = address(0xF00D);"
            )
        elif parameter_base == "bool":
            mutable_value = f"bool nextValue = !({current});"
        elif parameter_base.startswith(("uint", "int")):
            mutable_value = f"{parameter_base} nextValue = ({current}) == 0 ? 1 : 0;"
        if mutable_value is not None:
            arguments = tuple(
                "nextValue" if position == index else argument
                for position, argument in enumerate(arguments)
            )
            break
    if mutable_value is None:
        raise ValueError(
            f"no_matching_getter:{function.writes[0] if function.writes else '<no-modeled-write>'}; "
            "observer has no supported target-argument binding"
        )

    parameter_types = ",".join(parameter.type.split()[0] for parameter in function.parameters)
    argument_list = ", ".join(arguments)
    observer_arguments = ", ".join(arguments[index] for index in observer_indexes)
    observer_call = f"target.{state_getter}({observer_arguments})"
    state_snapshot = f"{state_type} beforeState = {observer_call};"
    state_after = observer_call
    if principal is not None:
        principal_setup = (
            f"address authorized = target.{principal}();\n"
            '        require(authorized != address(0), "CYDRA_MEASUREMENT_ASSERTION: authorized principal unavailable");\n'
            "        if (unauthorized == authorized) unauthorized = address(0xCAFD);"
        )
        control_lines = [
            "        vm.prank(unauthorized);",
            "        (bool unauthorizedOk,) = address(target).call(payload);",
            f"        if (unauthorizedOk && {state_after} != beforeState) {{",
            f'            require(false, "{security_assertion_marker()}: unauthorized caller mutated modeled administrative state");',
            "        }",
            "        require(",
            f"            !unauthorizedOk && {state_after} == beforeState,",
            '            "CYDRA_MEASUREMENT_ASSERTION: unauthorized differential control was not established"',
            "        );",
            "",
            "        vm.prank(authorized);",
            "        (bool authorizedOk,) = address(target).call(payload);",
            '        require(authorizedOk, "CYDRA_MEASUREMENT_ASSERTION: authorized control failed");',
            "        require(",
            f"            {state_after} != beforeState,",
            '            "CYDRA_MEASUREMENT_ASSERTION: authorized control did not change observed state"',
            "        );",
        ]
    else:
        # Without a source-derived authorized actor, an observed unauthorized
        # state mutation can still support the hypothesis. Failure to reproduce
        # it cannot establish rejection and must remain unmeasurable.
        principal_setup = ""
        control_lines = [
            "        vm.prank(unauthorized);",
            "        (bool unauthorizedOk,) = address(target).call(payload);",
            f"        if (unauthorizedOk && {state_after} != beforeState) {{",
            f'            require(false, "{security_assertion_marker()}: unauthorized caller mutated modeled administrative state");',
            "        }",
            '        require(false, "CYDRA_MEASUREMENT_ASSERTION: authorized control unavailable; cannot establish rejected");',
        ]
    control_body = "\n".join(control_lines)
    source = f'''// SPDX-License-Identifier: UNLICENSED
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
            {constructor_encoding}
        );
        address deployed;
        assembly {{
            deployed := create(0, add(initCode, 0x20), mload(initCode))
        }}
        require(deployed != address(0), "CYDRA: constructor deployment failed");
        target = {target_type}(payable(deployed));
    }}

    function testAuthorizationDifferentialOnModeledState() public {{
        address unauthorized = address(0xCAFE);
        {principal_setup}
        {state_snapshot}
        {mutable_value}
        bytes memory payload = abi.encodeWithSignature(
            "{function.name}({parameter_types})",
            {argument_list}
        );
        {control_body}
    }}
}}
'''
    path.write_text(source, encoding="utf-8")
    return path
