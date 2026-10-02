import importlib.util
from pathlib import Path
import unittest


LEASE_PATH = Path(__file__).resolve().parents[1] / "experiments" / "exp07" / "lease.py"
lease_spec = importlib.util.spec_from_file_location("exp07_lease", LEASE_PATH)
lease_module = importlib.util.module_from_spec(lease_spec)
lease_spec.loader.exec_module(lease_module)
GrantLease = lease_module.GrantLease


class GrantLeaseTests(unittest.TestCase):
    def test_renewal_expiry_and_revoke(self):
        lease = GrantLease(100, 30)
        self.assertTrue(lease.allows(129))
        self.assertTrue(lease.renew(120))
        self.assertEqual(lease.expiry_ns, 150)
        self.assertFalse(lease.allows(150))
        self.assertFalse(lease.renew(150))
        other = GrantLease(100, 30)
        other.revoke()
        self.assertFalse(other.allows(101))
        self.assertFalse(other.renew(101))

    def test_positive_window_required(self):
        with self.assertRaises(ValueError):
            GrantLease(0, 0)


if __name__ == "__main__":
    unittest.main()
