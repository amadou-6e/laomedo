"""Internal regression checks; not browser or real-profile acceptance evidence."""

import unittest
from uuid import uuid4

from pydantic import ValidationError

from laomedo.integrations.langflow.local_profiles.models import (
    ProfileCreateRequest,
    ProfileIndex,
    ProfileSummary,
)


class ProfileBoundaryTests(unittest.TestCase):
    def test_leading_zeroes_survive_but_credentials_cannot_be_serialized(self):
        request = ProfileCreateRequest(
            name="  Work  ", pin="001234", confirmation="001234"
        )
        self.assertEqual(request.name, "Work")
        self.assertEqual(request.pin.get_secret_value(), "001234")
        self.assertEqual(request.model_dump(), {"name": "Work"})
        self.assertNotIn("001234", repr(request))
        self.assertNotIn("001234", request.model_dump_json())

    def test_invalid_or_reserved_names_are_rejected(self):
        for name in (
            "",
            "  ",
            "__LAOMEDO_SYSTEM__",
            "__laomedo_system__ ",
            "a\nb",
            "x" * 41,
        ):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                ProfileCreateRequest(name=name, pin="001234", confirmation="001234")

    def test_pin_requires_ascii_digits_without_numeric_coercion(self):
        for pin in (
            123456,
            "12345",
            "1234567",
            "123 45",
            "\u0661\u0662\u0663\u0664\u0665\u0666",
            "abcdef",
        ):
            with self.subTest(pin=pin), self.assertRaises(ValidationError):
                ProfileCreateRequest(name="Work", pin=pin, confirmation=pin)

    def test_mismatched_pin_has_safe_error_text(self):
        with self.assertRaises(ValidationError) as error:
            ProfileCreateRequest(name="Work", pin="001234", confirmation="009876")
        self.assertNotIn("001234", str(error.exception))
        self.assertNotIn("009876", str(error.exception))
        self.assertIn("profile_pin_mismatch", str(error.exception))
        # API callers must additionally omit input/context from structured errors.
        safe = error.exception.errors(include_input=False, include_context=False)
        self.assertNotIn("001234", str(safe))

    def test_role_injection_and_upstream_user_fields_are_not_picker_fields(self):
        with self.assertRaises(ValidationError):
            ProfileCreateRequest(
                name="Work", pin="001234", confirmation="001234", is_superuser=True
            )
        with self.assertRaises(ValidationError):
            ProfileSummary(id=uuid4(), name="Work", password="not-a-picker-field")
        self.assertEqual(
            ProfileIndex().model_dump(mode="json"), {"profiles": [], "pin_digits": 6}
        )
