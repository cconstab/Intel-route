#!/usr/bin/env python3
"""
Bug: AtClient.notify() crashes when the AtKey has no iv_nonce set.

    def notify(self, at_key, value, ...):
        iv = at_key.metadata.iv_nonce            # None unless caller set it
        shared_key = self.get_encryption_key_shared_by_me(at_key)
        encrypted_value = EncryptionUtil.aes_encrypt_from_base64(value, shared_key, iv)

AES-CTR needs a nonce; passing iv=None raises
"argument should be a bytes-like object or ASCII string, not 'NoneType'".
notify() should generate a nonce itself (as put()/other paths effectively do),
so callers don't have to set metadata.iv_nonce manually.

This repro exercises the exact failing call with iv=None (no network needed).
"""
from at_client.util.encryptionutil import EncryptionUtil

shared_key = EncryptionUtil.generate_aes_key_base64()   # stand-in for the resolved shared key
try:
    EncryptionUtil.aes_encrypt_from_base64("hello", shared_key, None)  # iv as notify() passes it
    print("RESULT: OK — encryption tolerated a None nonce (unexpected)")
except Exception as e:
    print(f"RESULT: BUG — notify()'s aes_encrypt with unset iv_nonce raises: {type(e).__name__}: {e}")
