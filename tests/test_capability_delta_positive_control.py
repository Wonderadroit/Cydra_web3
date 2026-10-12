from pathlib import Path

from cydra.blind_authorization import generate_blind_authorization_test_from_experiment
from cydra.models import ContractModel, Experiment, FunctionModel, Hypothesis, ParameterModel


def test_positive_control_detects_new_role_membership(tmp_path: Path):
    fixture = (
        Path(__file__).parent
        / "fixtures"
        / "vulnerable_authority"
        / "VulnerableAuthority.sol"
    )
    source = fixture.read_text(encoding="utf-8")
    assert "function hasRole(bytes32 role, address account)" in source
    assert "function setTarget(address newTarget) external" in source
    assert "_roles[DEFAULT_ADMIN_ROLE][msg.sender] = true" in source

    model = ContractModel(
        name="VulnerableAuthority",
        source=str(fixture.resolve()),
        pragma="^0.8.22",
        state_variables=("target",),
        functions=(
            FunctionModel(
                name="setTarget",
                visibility="external",
                modifiers=(),
                writes=("target", "_roles"),
                external_calls=(),
                line=13,
                parameters=(ParameterModel(name="newTarget", type="address"),),
                source=str(fixture.resolve()),
            ),
        ),
    )
    hypothesis = Hypothesis(
        hypothesis_id="H-AUTH-setTarget",
        claim="setTarget may grant an unrelated caller an admin role",
        invariant_id="INV-AUTH-001",
        target_function="setTarget",
        attacker_capability="arbitrary external caller",
        expected_impact="attacker gains DEFAULT_ADMIN_ROLE on the existing target",
    )
    experiment = Experiment(
        experiment_id="X-H-AUTH-setTarget",
        hypothesis_id=hypothesis.hypothesis_id,
        action="Call setTarget as an unrelated actor and compare DEFAULT_ADMIN_ROLE membership before and after.",
        discriminates=(
            "caller gains DEFAULT_ADMIN_ROLE",
            "caller does not gain authority",
        ),
        cost=1.0,
        planned_inputs=("address(0xBEEF)",),
        target_function="setTarget",
    )
    generated = generate_blind_authorization_test_from_experiment(
        hypothesis,
        experiment,
        "../fixtures/vulnerable_authority/VulnerableAuthority.sol",
        "VulnerableAuthority",
        tmp_path / "GeneratedVulnerableAuthorityAuthTest.t.sol",
        model,
    ).read_text(encoding="utf-8")

    assert "target.hasRole(target.DEFAULT_ADMIN_ROLE(), address(attacker))" in generated
    assert "bool hadRoleBefore" in generated
    assert "bool hasRoleAfter" in generated
    assert "enum Verdict { None, Supported, Rejected, Inconclusive, Unmeasurable }" in generated
    assert "Verdict public verdict;" in generated
    assert "bool public deployed;" in generated
    assert "if (!hadRoleBefore && hasRoleAfter) verdict = Verdict.Supported;" in generated
    assert "assert(verdict != Verdict.None" in generated
    assert "emit CydraVerdict" not in generated
    assert "require(false" not in generated
    assert "hadRoleBefore != hasRoleAfter" in generated
