Branch: fix/put-get-random-iv
Title:  fix: use random IVs for stored keys (put/get), matching the Dart SDK

Related: #64 (adds random IVs for put/get via an IVNonce refactor — draft/stuck).
This PR is a minimal, backward-compatible alternative for the same gap.

---

`put`/`get` encrypted every stored value under a **static all-zero IV** (the default
of `aes_encrypt_from_base64`/`aes_decrypt_from_base64`), i.e. IV reuse across all
data. This makes the Python SDK match the Dart reference `at_client`:

- **Shared keys:** `put` always generates a random 16-byte IV and stores it as
  `ivNonce` in the key metadata (serialized into the update command).
- **Self keys:** also get a random IV (stored as `ivNonce`) — matching current Dart,
  which randomizes the IV for *every* put in `AtClientImpl._putInternal`
  (`at_client_impl.dart:973`) before dispatching to the encryptor. (Dart's per-type
  `SelfKeyEncryption` still has a dead zero-IV branch; a port must randomize self keys
  or it writes zero-IV data — which released atsdk does.) Interop-safe: `get` falls
  back to the zero IV when `ivNonce` is absent.
- **UpdateVerbBuilder:** fixed to carry `iv_nonce` — `set_metadata`/`_build_metadata_str`
  silently dropped it, so a self-key `ivNonce` would never have been persisted.
- **Get:** fetch metadata via `llookup:all` / `lookup:all`, use `ivNonce` when present,
  else fall back to the legacy zero IV — so existing data (and Dart-written legacy
  data) still decrypts.
- **Metadata:** `iv_nonce` kept as raw bytes internally (decode incoming base64) so it
  round-trips with `generate_iv_nonce()`/`__str__`.

Selection is purely by presence of `ivNonce`, matching Dart
(`legacy_encryption.dart` / `legacy_decryption.dart`: `ivNonce != null ? fromBase64 :
generateIVLegacy()`; legacy IV = 16 zero bytes).

**Tests**
- `test/put_get_iv_test.py` — network-free: AES round-trip with a random IV; legacy IV
  is 16 zero bytes; `Metadata` iv_nonce base64<->bytes round-trip; `_iv_from_fetched`;
  and `_put_shared_key` generates + persists a 16-byte IV.
- **Cross-SDK interop verified** against the Dart reference `at_client`, both
  directions, for shared keys (random IV):
  - Python `put` shared → Dart `get` shared ✅
  - Dart `put` shared → Python `get` shared ✅

**Backward compatibility:** absent `ivNonce` ⇒ zero IV, so all pre-existing data
(Python- or Dart-written) still decrypts.
