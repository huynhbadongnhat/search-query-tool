"""API-key persistence helpers with verified clear semantics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

ReadStatus = Literal["found", "absent", "failed"]
DeleteStatus = Literal["removed", "absent", "failed"]


@dataclass(frozen=True)
class ReadResult:
    """Result from reading one credential backend."""

    status: ReadStatus
    value: str = ""


@dataclass(frozen=True)
class ClearResult:
    """Outcome of a clear-key operation with post-deletion verification."""

    kr_status: DeleteStatus
    pt_status: DeleteStatus
    kr_verify_status: ReadStatus
    pt_verify_status: ReadStatus

    @property
    def verified_gone(self) -> bool:
        """True only when both backends were read and confirmed empty."""
        return self.kr_verify_status == "absent" and self.pt_verify_status == "absent"

    @property
    def success(self) -> bool:
        """True only for clean removal with no backend failures."""
        return self.verified_gone and self.kr_status != "failed" and self.pt_status != "failed"

    @property
    def warning(self) -> bool:
        """True when no key remains but at least one delete operation failed."""
        return self.verified_gone and not self.success

    @property
    def message(self) -> str:
        """Human-readable summary for UI display."""
        if self.success:
            parts = []
            if self.kr_status == "removed":
                parts.append("OS keychain")
            if self.pt_status == "removed":
                parts.append("plaintext file")
            if parts:
                return f"Key cleared from {' and '.join(parts)}."
            return "Key was already absent."

        if self.warning:
            return (
                "No saved key remains, but at least one storage backend reported "
                "a deletion error. Review logs if this repeats."
            )

        problems = []
        if self.kr_verify_status == "found":
            problems.append("OS keychain still contains a saved key")
        elif self.kr_verify_status == "failed":
            problems.append("OS keychain removal could not be verified")
        elif self.kr_status == "failed":
            problems.append("OS keychain deletion failed")

        if self.pt_verify_status == "found":
            problems.append("plaintext key file still exists")
        elif self.pt_verify_status == "failed":
            problems.append("plaintext key file removal could not be verified")
        elif self.pt_status == "failed":
            problems.append("plaintext key file deletion failed")

        if not problems:
            problems.append("local key removal could not be verified")
        return "Key may still be stored: " + "; ".join(problems) + "."


def keyring_available() -> bool:
    """Return True if the keyring package can be imported."""
    try:
        import keyring  # type: ignore  # noqa: F401

        return True
    except Exception:
        return False


def read_keyring(service: str, username: str) -> ReadResult:
    """Read a keyring credential, preserving read failures as failures."""
    try:
        import keyring  # type: ignore

        value = keyring.get_password(service, username)
    except Exception:
        return ReadResult("failed")

    value = value.strip() if value else ""
    if value:
        return ReadResult("found", value)
    return ReadResult("absent")


def set_keyring(service: str, username: str, value: str) -> bool:
    """Store a credential in keyring."""
    try:
        import keyring  # type: ignore

        keyring.set_password(service, username, value)
        return True
    except Exception:
        return False


def delete_keyring(service: str, username: str) -> DeleteStatus:
    """Delete a keyring credential when present."""
    existing = read_keyring(service, username)
    if existing.status == "absent":
        return "absent"
    if existing.status == "failed":
        return "failed"

    try:
        import keyring  # type: ignore

        keyring.delete_password(service, username)
        return "removed"
    except Exception:
        return "failed"


def read_plaintext(path: Path) -> ReadResult:
    """Read a plaintext key file, preserving read failures as failures."""
    try:
        if not path.exists():
            return ReadResult("absent")
        value = path.read_text().strip()
    except Exception:
        return ReadResult("failed")

    if value:
        return ReadResult("found", value)
    return ReadResult("absent")


def save_plaintext(path: Path, value: str) -> bool:
    """Write a plaintext fallback key file."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value)
        try:
            path.chmod(0o600)
        except Exception:
            pass
        return True
    except Exception:
        return False


def delete_plaintext(path: Path) -> DeleteStatus:
    """Delete a plaintext key file when present."""
    try:
        if not path.exists():
            return "absent"
        path.unlink()
        return "removed"
    except Exception:
        return "failed"


def load_saved_key(service: str, username: str, plaintext_path: Path) -> str:
    """Load a saved key, preferring keyring and falling back to plaintext."""
    keyring_result = read_keyring(service, username)
    if keyring_result.status == "found":
        return keyring_result.value

    plaintext_result = read_plaintext(plaintext_path)
    if plaintext_result.status == "found":
        return plaintext_result.value
    return ""


def save_key(service: str, username: str, plaintext_path: Path, value: str) -> str:
    """Save a key. Returns 'keyring', 'plaintext', or '' on failure."""
    if set_keyring(service, username, value):
        return "keyring"
    if save_plaintext(plaintext_path, value):
        return "plaintext"
    return ""


def clear_key(service: str, username: str, plaintext_path: Path) -> ClearResult:
    """Delete a saved key from both backends and verify the final state."""
    kr_status = delete_keyring(service, username)
    pt_status = delete_plaintext(plaintext_path)
    kr_verify = read_keyring(service, username)
    pt_verify = read_plaintext(plaintext_path)

    return ClearResult(
        kr_status=kr_status,
        pt_status=pt_status,
        kr_verify_status=kr_verify.status,
        pt_verify_status=pt_verify.status,
    )
