import pytest

from src.testing.test_environment import (
    UnsafeTestEnvironment,
    assert_test_environment,
)


@pytest.mark.parametrize(
    ("env_name", "profile_name"),
    [
        (None, "local"),
        ("prod", "local"),
        ("test", None),
        ("test", "migration"),
    ],
)
def test_environment_requires_test_and_local(
    env_name: str | None,
    profile_name: str | None,
) -> None:
    with pytest.raises(UnsafeTestEnvironment):
        assert_test_environment(env_name, profile_name)


def test_environment_accepts_case_and_surrounding_space() -> None:
    assert_test_environment(" TEST ", " LOCAL ")
