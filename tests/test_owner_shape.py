from types import SimpleNamespace

from cydra.capabilities import AuthorityShape, OwnerShape


def _function(*modifiers):
    return SimpleNamespace(modifiers=tuple(modifiers))


def test_owner_shape_preserves_legacy_public_owner_guard_detection():
    source = """
    contract Target {
        address public owner;
        modifier onlyOwner() { require(msg.sender == owner, 'owner'); _; }
    }
    """
    shape = OwnerShape()
    function = _function("onlyOwner")

    assert isinstance(shape, AuthorityShape)
    assert shape.detect(source, function)
    assert shape.resolve_authorized(source, function) == "owner"
    assert not shape.verify_role(source, function)


def test_owner_shape_accepts_reversed_sender_equality():
    source = """
    contract Target {
        address public owner;
        modifier onlyOwner() { require(owner == msg.sender, 'owner'); _; }
    }
    """
    assert OwnerShape().resolve_authorized(source, _function("onlyOwner")) == "owner"


def test_owner_shape_fails_closed_without_public_address_principal():
    source = """
    contract Target {
        address private owner;
        modifier onlyOwner() { require(msg.sender == owner, 'owner'); _; }
    }
    """
    shape = OwnerShape()
    function = _function("onlyOwner")
    assert not shape.detect(source, function)
    assert shape.resolve_authorized(source, function) is None


def test_owner_shape_does_not_infer_owner_from_unrelated_modifier():
    source = """
    contract Target {
        address public owner;
        modifier onlyOwner() { require(msg.sender == owner, 'owner'); _; }
    }
    """
    assert OwnerShape().resolve_authorized(source, _function("whenPaused")) is None
