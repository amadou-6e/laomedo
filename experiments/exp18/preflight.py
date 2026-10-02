"""Check an E05 Docker create result against the reviewed grant before start."""

from pathlib import Path


def _source(mount):
    if mount.get("Type") == "bind":
        return str(Path(mount.get("Source", "")).resolve()).casefold()
    return mount.get("Name", "")


def validate_inspect(inspected, expected_mounts, network):
    """Return fail-closed mismatch codes for one `docker inspect` object.

    expected_mounts maps a container target to (type, source/name, writable).
    The caller must construct and review this manifest before Docker create.
    """
    errors = []
    host = inspected.get("HostConfig") or {}
    config = inspected.get("Config") or {}
    if host.get("ReadonlyRootfs") is not True:
        errors.append("root_not_read_only")
    if "ALL" not in (host.get("CapDrop") or []):
        errors.append("capabilities_not_dropped")
    if not any(option.startswith("no-new-privileges") for option in
               (host.get("SecurityOpt") or [])):
        errors.append("new_privileges_allowed")
    if host.get("PidsLimit") != 128:
        errors.append("pid_limit_mismatch")
    if host.get("Memory") != 1024 ** 3:
        errors.append("memory_limit_mismatch")
    if config.get("User") != "10001:10001":
        errors.append("user_mismatch")
    if host.get("NetworkMode") != network:
        errors.append("network_mismatch")
    if host.get("Privileged") is not False:
        errors.append("privileged_or_unknown")
    actual = {mount.get("Destination"): mount for mount in
              (inspected.get("Mounts") or [])}
    if len(actual) != len(inspected.get("Mounts") or []):
        errors.append("duplicate_mount_target")
    if set(actual) != set(expected_mounts):
        errors.append("mount_set_mismatch")
    for target, (kind, source, writable) in expected_mounts.items():
        mount = actual.get(target)
        if mount is None:
            continue
        expected_source = (str(Path(source).resolve()).casefold()
                           if kind == "bind" else source)
        if (mount.get("Type") != kind or _source(mount) != expected_source or
                mount.get("RW") is not writable):
            errors.append("mount_mismatch:" + target)
    return errors
