"""Shared model-metadata assertions; these do not execute providers or services."""

import importlib
from pydantic import BaseModel


def assert_described_models(*module_names):
    """Reject empty/forwarding model owners and undocumented local fields."""
    for name in module_names:
        module = importlib.import_module("laomedo." + name)
        models = [
            value
            for value in vars(module).values()
            if isinstance(value, type)
            and issubclass(value, BaseModel)
            and value.__module__ == module.__name__
        ]
        if not models:
            raise AssertionError("Model owner has no local models: " + name)
        for model in models:
            for field_name, field in model.model_fields.items():
                if not field.description or not field.description.strip():
                    raise AssertionError(
                        f"{name}.{model.__name__}.{field_name} is undescribed"
                    )
