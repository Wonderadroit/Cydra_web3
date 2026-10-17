"""Capability interfaces and evidence-backed shapes for CYDRA."""

from .authority_shape import AuthorityShape
from .observation import ObservationMethod
from .write_form import WriteForm
from .owner_shape import OwnerShape
from .public_getter_observation import PublicGetterObservation
from .scalar_write import ScalarWrite
from .nested_mapping_write import NestedMappingWrite

__all__ = [
    "AuthorityShape",
    "ObservationMethod",
    "WriteForm",
    "OwnerShape",
    "PublicGetterObservation",
    "ScalarWrite",
    "NestedMappingWrite",
]
