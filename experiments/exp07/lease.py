"""Monotonic external-write grant expiry model for the synthetic canary."""


class GrantLease:
    def __init__(self, now_ns, lease_ns):
        if lease_ns <= 0:
            raise ValueError("positive_lease_required")
        self.lease_ns = lease_ns
        self.expiry_ns = now_ns + lease_ns
        self.revoked = False

    def allows(self, now_ns):
        return not self.revoked and now_ns < self.expiry_ns

    def renew(self, now_ns):
        if not self.allows(now_ns):
            return False
        self.expiry_ns = now_ns + self.lease_ns
        return True

    def revoke(self):
        self.revoked = True
