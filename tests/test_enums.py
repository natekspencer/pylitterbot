from pylitterbot.enums import LitterBoxStatus


def test_drawer_full_statuses():
    """Tests the drawer full statuses are as expected."""
    statuses = LitterBoxStatus.get_drawer_full_statuses(codes_only=True)
    assert set(statuses) == set(["DF1", "DF2", "DFS", "SDF"])
