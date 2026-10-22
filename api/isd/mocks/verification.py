class MockContactVerifier:
    """Synthetic numbers (555) pass. Attorney contacts always say a bar check is still needed."""

    def verify(self, contact_type: str, phone_ref: str) -> str:
        if contact_type == "attorney":
            return "stub_needs_bar_check"
        digits = "".join(c for c in phone_ref if c.isdigit())
        return "stub_verified" if digits.startswith("555") else "stub_unverified"
