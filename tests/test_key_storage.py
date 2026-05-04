import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.key_storage import clear_key, load_saved_key


class FakeKeyring:
    def __init__(self, get_results=None, delete_error=False):
        self.get_results = list(get_results or [])
        self.delete_error = delete_error
        self.deleted = False

    def get_password(self, service, username):
        if self.get_results:
            result = self.get_results.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        return None

    def set_password(self, service, username, value):
        return None

    def delete_password(self, service, username):
        if self.delete_error:
            raise RuntimeError("delete failed")
        self.deleted = True
        return None


class KeyStorageTests(unittest.TestCase):
    def test_clear_fails_when_keyring_verification_fails(self):
        fake_keyring = FakeKeyring(
            get_results=[
                "secret",
                RuntimeError("verification failed"),
            ],
            delete_error=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            key_file = Path(tmpdir) / "api_key.txt"
            with patch.dict(sys.modules, {"keyring": fake_keyring}):
                result = clear_key("svc", "user", key_file)

        self.assertEqual("failed", result.kr_status)
        self.assertEqual("failed", result.kr_verify_status)
        self.assertFalse(result.verified_gone)
        self.assertFalse(result.success)
        self.assertFalse(result.warning)
        self.assertIn("could not be verified", result.message)

    def test_clear_succeeds_only_when_backends_are_confirmed_absent(self):
        fake_keyring = FakeKeyring(get_results=[None, None])

        with tempfile.TemporaryDirectory() as tmpdir:
            key_file = Path(tmpdir) / "api_key.txt"
            with patch.dict(sys.modules, {"keyring": fake_keyring}):
                result = clear_key("svc", "user", key_file)

        self.assertEqual("absent", result.kr_status)
        self.assertEqual("absent", result.pt_status)
        self.assertTrue(result.verified_gone)
        self.assertTrue(result.success)
        self.assertFalse(result.warning)

    def test_clear_warns_when_delete_failed_but_absence_is_verified(self):
        fake_keyring = FakeKeyring(
            get_results=[
                "secret",
                None,
            ],
            delete_error=True,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            key_file = Path(tmpdir) / "api_key.txt"
            with patch.dict(sys.modules, {"keyring": fake_keyring}):
                result = clear_key("svc", "user", key_file)

        self.assertEqual("failed", result.kr_status)
        self.assertEqual("absent", result.kr_verify_status)
        self.assertTrue(result.verified_gone)
        self.assertFalse(result.success)
        self.assertTrue(result.warning)

    def test_load_saved_key_falls_back_to_plaintext_after_keyring_failure(self):
        fake_keyring = FakeKeyring(get_results=[RuntimeError("read failed")])

        with tempfile.TemporaryDirectory() as tmpdir:
            key_file = Path(tmpdir) / "api_key.txt"
            key_file.write_text("plaintext-secret")
            with patch.dict(sys.modules, {"keyring": fake_keyring}):
                value = load_saved_key("svc", "user", key_file)

        self.assertEqual("plaintext-secret", value)


if __name__ == "__main__":
    unittest.main()
