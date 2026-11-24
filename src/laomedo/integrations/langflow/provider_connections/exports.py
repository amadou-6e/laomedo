"""Portable flow sanitization for local provider-account selectors."""

from copy import deepcopy


def strip_local_bindings(value):
    """Copy JSON data and clear local bindings/options on export and file import.

    Opaque selectors are not credentials, but they are machine/profile-local
    authority choices. Imports require an explicit selection on the new host.
    Other fields and retained run evidence keep their existing export policy.
    """
    if isinstance(value, list):
        return [strip_local_bindings(item) for item in value]
    if not isinstance(value, dict):
        return deepcopy(value)
    result = {key: strip_local_bindings(item) for key, item in value.items()}
    result.pop("laomedo_authoring_bindings", None)
    field = result.get("provider_connection")
    if isinstance(field, dict):
        field.update(value="", options=[], options_metadata=[])
    return result
