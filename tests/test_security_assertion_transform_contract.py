from pathlib import Path

from scripts.run_authorization_campaign import _patched_auth_test


def test_generated_security_assertion_is_accepted_by_patch_transformer(tmp_path: Path) -> None:
    generated = tmp_path / "H-AUTH-setRouter.t.sol"
    destination = tmp_path / "H-AUTH-setRouter.patched.t.sol"
    generated.write_text(
        """
        function testAuthorizationDifferentialOnModeledState() public {
            bool unauthorizedOk = true;
            bool stateChanged = true;
            bool ok = !(unauthorizedOk && (stateChanged != false));
            require(ok, "CYDRA_SECURITY_ASSERTION: unauthorized caller mutated modeled administrative state");
            require(!unauthorizedOk, "CYDRA_MEASUREMENT_ASSERTION: unauthorized differential control was not established");
        }
        """,
        encoding="utf-8",
    )

    _patched_auth_test(generated, destination)

    patched = destination.read_text(encoding="utf-8")
    assert "if (!ok) return;" in patched
    assert 'require(ok, "CYDRA_SECURITY_ASSERTION:' not in patched
    # The unrelated measurement assertion must remain intact.
    assert 'require(!unauthorizedOk, "CYDRA_MEASUREMENT_ASSERTION:' in patched
