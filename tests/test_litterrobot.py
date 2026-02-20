"""Test LitterRobot property type consistency across models."""

# pylint: disable=protected-access
from __future__ import annotations

import functools
import inspect
from itertools import combinations
from typing import get_type_hints

import pytest

from pylitterbot.robot.litterrobot3 import LitterRobot3
from pylitterbot.robot.litterrobot4 import LitterRobot4
from pylitterbot.robot.litterrobot5 import LitterRobot5

CLASSES = [LitterRobot3, LitterRobot4, LitterRobot5]


def get_properties_with_types(cls: type) -> dict[str, object]:
    """Get properties with types."""
    properties: dict[str, object] = {}

    for name, member in inspect.getmembers(cls):
        if isinstance(member, property):
            # Get return type annotation from the fget
            hints = get_type_hints(member.fget)
            properties[name] = hints.get("return")

    return properties


@functools.lru_cache
@pytest.mark.parametrize("cls_a, cls_b", combinations(CLASSES, 2))
@pytest.mark.parametrize(
    "prop_name",
    sorted(set().union(*[get_properties_with_types(c).keys() for c in CLASSES])),
)
def test_property_type_pairwise(cls_a: type, cls_b: type, prop_name: str) -> None:
    """Test property type matches."""
    props_a = get_properties_with_types(cls_a)
    props_b = get_properties_with_types(cls_b)

    if prop_name in props_a and prop_name in props_b:
        assert props_a[prop_name] == props_b[prop_name]
