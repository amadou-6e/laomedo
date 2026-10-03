"""Check an E05 Docker create result against the reviewed grant before start."""

from pathlib import Path


def validate_host_roots(roots):
    """Refuse aliased, missing or overlapping fixture roots before create."""
    required = {"checkout", "effective_skill", "canonical_skill", "host",
                "runner_store", "credential_standin"}
    errors = []
    if set(roots) != required:
        errors.append("root_set_mismatch")
    resolved = {}
    for role, value in roots.items():
        path = Path(value)
        if not path.is_dir():
            errors.append("missing_root:" + role)
            continue
        canonical = path.resolve(strict=True)
        if str(path.absolute()).casefold() != str(canonical).casefold():
            errors.append("aliased_root:" + role)
        resolved[role] = canonical
    for left, first in resolved.items():
        for right, second in resolved.items():
            if left >= right:
                continue
            if first == second or first.is_relative_to(second) or second.is_relative_to(first):
                errors.append("overlapping_roots:" + left + ":" + right)
    return errors


def _source(mount):
    if mount.get("Type") == "bind":
        return str(Path(mount.get("Source", "")).resolve()).casefold()
    return mount.get("Name", "")


def validate_inspect(inspected, expected_mounts, network, image_id, tmpfs):
    """Return fail-closed mismatch codes for one `docker inspect` object.

    expected_mounts maps a container target to (type, source/name, writable).
    tmpfs maps each approved scratch target to its exact Docker option string.
    The caller must construct and review this manifest before Docker create.
    """
    errors = []
    host = inspected.get("HostConfig") or {}
    config = inspected.get("Config") or {}
    if inspected.get("Image") != image_id:
        errors.append("image_id_mismatch")
    if host.get("ReadonlyRootfs") is not True:
        errors.append("root_not_read_only")
    if host.get("CapDrop") != ["ALL"]:
        errors.append("capabilities_not_dropped")
    if host.get("CapAdd") not in (None, []):
        errors.append("capabilities_added")
    if host.get("SecurityOpt") not in (["no-new-privileges"],
                                       ["no-new-privileges:true"]):
        errors.append("security_options_mismatch")
    for field, allowed in (("PidMode", ("",)), ("IpcMode", ("private",)),
                           ("UTSMode", ("",)), ("UsernsMode", ("",))):
        if host.get(field) not in allowed:
            errors.append(field.lower() + "_mismatch")
    if host.get("Devices") not in (None, []):
        errors.append("devices_present")
    if host.get("DeviceRequests") not in (None, []):
        errors.append("device_requests_present")
    if host.get("Tmpfs") != tmpfs:
        errors.append("tmpfs_mismatch")
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
    mounted = inspected.get("Mounts") or []
    mounted_tmpfs = {mount.get("Destination") for mount in mounted
                    if mount.get("Type") == "tmpfs"}
    if mounted_tmpfs and mounted_tmpfs != set(tmpfs):
        errors.append("tmpfs_mount_set_mismatch")
    regular = [mount for mount in mounted if mount.get("Type") != "tmpfs"]
    actual = {mount.get("Destination"): mount for mount in regular}
    if len(actual) != len(regular):
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
