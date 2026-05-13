"""Lock crypto envelope smoke test (Phase 1 of plans/lock_my_user_data.md).

Drives the worker's __lockSelfTest RPC, which round-trips a known plaintext
through lockBlobWithPassphrase + unlockBlobWithPassphrase and asserts:

  - envelope starts with the EHFLOCK magic
  - right passphrase decrypts to identical bytes
  - wrong passphrase fails with WebCrypto's OperationError
  - header parameters match the v1 spec (kdf id, iter count, lengths)

The OPFS-touching RPCs (enableLock, unlock, lock, changePassphrase,
disableLock) and the locked-boot UX land in later phases; this test is
the foundation that proves the crypto layer is sound in isolation.
"""
from __future__ import annotations


def test_lock_self_test_roundtrip(worker_data):
    result = worker_data.page.evaluate(
        "() => window.__dataProvider._rpc.call('__lockSelfTest')"
    )
    assert result.get("ok") is True, result
    assert result["plainLen"] > 0
    # Header: 8 magic + 1 version + 1 kdfId + 4 iters + 2 saltLen
    #         + 16 salt + 12 iv = 44 fixed bytes;
    # ciphertext = plaintext + 16-byte GCM auth tag.
    expected_envelope_len = 44 + result["plainLen"] + 16
    assert result["envelopeLen"] == expected_envelope_len, result

    header = result["header"]
    assert header["formatVersion"] == 1
    assert header["kdfId"] == 1  # PBKDF2-SHA256
    assert header["iters"] == 600000
    assert header["saltLen"] == 16
    assert header["ivLen"] == 12
    assert header["ciphertextLen"] == result["plainLen"] + 16


def test_lock_wrong_passphrase_is_operation_error(worker_data):
    result = worker_data.page.evaluate(
        "() => window.__dataProvider._rpc.call('__lockSelfTest')"
    )
    assert result.get("ok") is True, result
    # WebCrypto's GCM auth-tag failure surfaces as a DOMException with
    # name === 'OperationError'. We rely on this distinction in Phase 2's
    # `unlock` RPC to differentiate "wrong passphrase" from "envelope is
    # corrupt" — if browsers ever changed the name, that branch would
    # silently mis-handle the case, so we pin it here.
    assert result["wrongPassphraseErrorName"] == "OperationError", result
