# Claude Fix Brief: API Key Clear Must Verify Removal

## Context

Codex reviewed Claude's latest portable-build pass. Most previous findings are addressed, but one security-relevant API-key handling issue remains in `app.py`.

This app is intended to run portably on user machines, and API keys must be handled conservatively. The UI must not say a key was cleared unless the stored credential is actually gone, or unless the app can clearly report that only part of the clear operation succeeded.

## Finding to Fix

### Clear key can falsely report success

Location:

- `app.py`, `clear_saved_api_key()`, around lines 205-209
- `app.py`, `clear_saved_umls_api_key()`, around lines 254-258

Problem:

- `clear_saved_api_key()` combines keyring deletion and plaintext deletion with `ok_kr or ok_pt`.
- `_plaintext_delete()` returns `True` when the plaintext file is absent.
- Therefore, clear can report success even when keyring deletion fails and the API key remains in the OS keychain.
- The same issue exists for `clear_saved_umls_api_key()`.

Why this matters:

- The app handles private API keys.
- A false success message can leave credentials behind while telling the user they were removed.
- For a portable/security-focused tool, this is unacceptable.

## Required Fix

Replace the boolean-only clear flow with a result that distinguishes:

- keyring credential removed
- keyring credential was already absent
- keyring removal failed
- plaintext file removed
- plaintext file was already absent
- plaintext removal failed
- final verification result

Recommended approach:

1. Add a small structured result type, such as a `dataclass`, for clear operations.
2. Make low-level delete helpers report three states instead of a simple boolean:
   - `"removed"`
   - `"absent"`
   - `"failed"`
3. After attempting deletion, verify by reading both storage locations again:
   - keyring: `_try_keyring_get(service, username)`
   - plaintext: `_plaintext_load(path)`
4. Treat clear as successful only when no stored value remains in either location.
5. Update the UI messages:
   - Show success only if verification confirms the key is gone.
   - Show warning if one backend failed but verification shows no key remains.
   - Show error if a stored key remains or verification is inconclusive.
6. Apply the same behavior to both NanoGPT and UMLS API keys.

Keep the current priority behavior for reading keys:

- session state first
- Streamlit secrets
- environment variables
- saved storage only when "Remember keys on this computer" is enabled

Do not clear environment variables or Streamlit secrets. The clear button should only clear saved local storage.

## Acceptance Criteria

- If keyring deletion fails and no plaintext file exists, the UI does not show a plain success message.
- If a key remains retrievable from keyring after clearing, the UI reports failure.
- If the plaintext file remains after clearing, the UI reports failure.
- If both saved storage locations are absent after clearing, the UI reports success.
- The behavior is identical for NanoGPT and UMLS keys.
- No plaintext fallback is silently treated as proof that keyring was cleared.

## Verification

Run:

```powershell
uv run python -m compileall app.py src tests -q
uv run python -m unittest discover -s tests
git diff --check
```

Manual checks:

1. Save a NanoGPT key with "Remember keys on this computer" enabled.
2. Clear it.
3. Confirm the UI only reports success if the key is no longer loaded after refresh.
4. Repeat the same flow for the UMLS key.
5. Simulate keyring failure if practical, for example by temporarily making the keyring delete helper return failure, and confirm the UI does not claim full success.

## Do Not

- Do not change query-generation logic.
- Do not make key persistence default-on.
- Do not clear Streamlit secrets or environment variables.
- Do not write keys to the USB/app directory.
- Do not reintroduce the older fixed portable-build issues.
