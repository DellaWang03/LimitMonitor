"""Explicit environment gates for isolated, non-production runs."""


class UnsafeTestEnvironment(RuntimeError):
    """The caller did not prove an approved test environment."""


def assert_test_environment(
    env_name: str | None,
    profile_name: str | None,
) -> None:
    if (env_name or "").strip().lower() != "test":
        raise UnsafeTestEnvironment("ENV 必须为 test")
    if (profile_name or "").strip().lower() != "local":
        raise UnsafeTestEnvironment("LIMIT_MONITOR_PROFILE 必须为 local")
