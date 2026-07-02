# Dart-matched IV/ivNonce spec for stored-key put/get (Python at_python)

Derived from the Dart reference SDK (`at_client_sdk`) so the Python fix is
wire-compatible. All references are Dart unless noted.

## Representation
- `ivNonce` = **base64 string** of a **16-byte** IV, carried in key metadata.
- **Legacy IV = 16 zero bytes.**
  - `getIV(null)` → `IV(Uint8List(16))` — `aes_converter.dart:112`
  - `AtChopsUtil.generateIVLegacy()` → `InitialisationVector(IV(Uint8List(16)).bytes)` — `at_chops_util.dart:34`
  - (Python's current default `b'\x00'*16` already equals this.)
- Random IV = `IV.fromSecureRandom(16)`; `EncryptionUtil.generateIV()` returns its
  base64 — `encryption_util.dart:28`.

## Selection rule (legacy vs random) — everywhere
Purely **presence of `ivNonce` in metadata**. No preference flag or version gate:
```dart
if (atKey.metadata.ivNonce != null) iV = generateIVFromBase64String(ivNonce);
else                                 iV = generateIVLegacy();   // 16 zero bytes
```
(`legacy_decryption.dart:87/137/224`, `legacy_encryption.dart:366`)

## PUT / encrypt
- **Shared key:** always ensure a random IV, then persist it:
  ```dart
  atKey.metadata.ivNonce ??= EncryptionUtil.generateIV();          // random 16B, base64
  iV = AtChopsUtil.generateIVFromBase64String(atKey.metadata.ivNonce!);
  ```
  (`legacy_encryption.dart:410-413`) → new shared data ALWAYS gets a random IV.
- **Self key:** use `ivNonce` if the caller set it, else legacy zero IV — **no
  auto-generate** (`legacy_encryption.dart:363-368`).
- The IV rides along because metadata is serialized into the update command
  (Python `Metadata.__str__` already emits `:ivNonce:<b64>`).

## GET / decrypt (self + shared, both directions)
- Read `ivNonce` from the fetched key's **metadata**; use it, else legacy zero IV.
- Implies the value lookup must **return metadata** — Dart's lookup does. **Python's
  value-get currently uses plain `llookup:` (value only, atclient.py:133/300)**, so to
  match Dart it must fetch metadata too (e.g. `llookup:all:` and parse the JSON's
  `metadata.ivNonce`).

## Python implementation checklist
1. `_put_shared_key`: `key.metadata.iv_nonce = key.metadata.iv_nonce or generate_iv_nonce_b64()`; encrypt with `b64decode(iv_nonce)`. (IV already persists via `Metadata.__str__`.)
2. `_put_self_key`: `iv = b64decode(iv_nonce) if iv_nonce else b'\x00'*16`.
3. All get paths (`_get_self_key`, `_get_shared_by_me_with_other`,
   `_get_shared_by_other_with_me`): switch to `llookup:all:`, parse `metadata.ivNonce`,
   `iv = b64decode(ivNonce) if present else b'\x00'*16`, decrypt.
4. **Normalize `iv_nonce` representation** — currently inconsistent: `Metadata.__str__`
   does `binascii.b2a_base64(self.iv_nonce)` (expects **bytes**) while
   `Metadata.from_json` sets it from `data.get('ivNonce')` (a base64 **string**). Pick
   base64-string end-to-end and make `generate_iv_nonce`, `__str__`, and `from_json`
   agree (this muddle is likely what forced PR #64's `IVNonce` class).
5. Backward compatible by construction: absent `ivNonce` → zero IV, so all existing
   data (and Dart-written legacy data) still decrypts.

## Notes
- Matches Dart's asymmetry: shared put auto-randomizes; self put stays legacy unless
  `ivNonce` is set. (Can revisit self-key randomization separately.)
- `notify()` (our PR #1) already generates a random IV and sets metadata — consistent
  with the shared-put behavior here.
