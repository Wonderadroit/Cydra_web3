from cydra.authorization_pipeline import _hypotheses_from_derived_write_seeds
from cydra.hypothesis_seeds import HypothesisSeed
from cydra.models import Hypothesis


def _seed(
    *,
    function="configure",
    status="seed",
    invariant_source="derived",
    writes=("registry",),
):
    return HypothesisSeed(
        seed_id=f"SEED-AUTH-Registry-{function}-12",
        target_contract="Registry",
        target_function=function,
        question=f"Can an unauthorized caller change state through {function}?",
        invariant="Only an evidenced authorized actor may change security-relevant state.",
        invariant_source=invariant_source,
        falsification=f"Call {function} as an unrelated actor and inspect state.",
        preconditions_needed=("deployment_or_local_fork", "intended_authorization_boundary"),
        status=status,
        source="src/Registry.sol",
        source_line=12,
        observed_writes=writes,
        provenance=("source:src/Registry.sol:12", "observed_write:registry"),
        uncertainty=("effective guards require runtime validation",),
    )


def test_derived_write_seed_becomes_candidate_without_admin_name_prefix():
    candidates = _hypotheses_from_derived_write_seeds((_seed(function="configure"),), ())

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.target_function == "configure"
    assert candidate.invariant_id == "INV-AUTH-001"
    assert candidate.evidence_ids == ("E-SEED-SEED-AUTH-Registry-configure-12",)
    assert "registry" in candidate.expected_impact


def test_blocked_generic_or_lifecycle_seed_is_not_promoted():
    seeds = (
        _seed(function="executeMetaTxn", status="blocked", invariant_source="generic", writes=()),
        _seed(function="initializeRegistry", status="blocked", invariant_source="generic"),
    )

    assert _hypotheses_from_derived_write_seeds(seeds, ()) == ()


def test_existing_candidate_prevents_duplicate_seed_candidate():
    existing = (
        Hypothesis(
            hypothesis_id="H-AUTH-configure",
            claim="Existing candidate",
            invariant_id="INV-AUTH-001",
            target_function="configure",
            attacker_capability="arbitrary external caller",
            expected_impact="state change",
        ),
    )

    assert _hypotheses_from_derived_write_seeds((_seed(function="configure"),), existing) == ()
