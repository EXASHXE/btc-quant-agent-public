"""Legacy service API is disabled in the isolated swing product."""


def create_app(*args, **kwargs):
    raise RuntimeError("LEGACY_API_OUT_OF_ACTIVE_SCOPE_USE_OFFLINE_SNAPSHOT_RENDERER")
