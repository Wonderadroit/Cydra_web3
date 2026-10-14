from pathlib import Path

from cydra.blind_authorization import _resolve_inherited_ownable_surface


def test_resolves_inherited_owner_getter_with_minimal_sibling_fixture(tmp_path: Path):
    source = tmp_path / "InheritedAuthority.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract OwnableBase {
            address public owner;
            modifier onlyOwner() { require(msg.sender == owner, "owner only"); _; }
        }
        contract Target is OwnableBase {
            address public router;
            function setRouter(address next) external { router = next; }
            function guardedSibling(address next) external onlyOwner { router = next; }
        }
        """,
        encoding="utf-8",
    )

    supported, reason, surface = _resolve_inherited_ownable_surface(source, "Target")

    assert supported is True
    assert reason == "owner_getter_resolved"
    assert "owner" in surface


def test_inherited_authority_walk_fails_closed_when_depth_budget_exhausted(tmp_path: Path):
    source = tmp_path / "DeepInheritance.sol"
    source.write_text(
        """
        pragma solidity ^0.8.20;
        contract Base0 { address public owner; }
        contract Base1 is Base0 {}
        contract Base2 is Base1 {}
        contract Base3 is Base2 {}
        contract Target is Base3 {}
        """,
        encoding="utf-8",
    )

    supported, reason, _ = _resolve_inherited_ownable_surface(
        source, "Target", depth_budget=2
    )

    assert supported is False
    assert reason == "authority_inheritance_depth_exceeded:2"
