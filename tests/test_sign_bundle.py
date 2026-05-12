"""Tests for scripts/sign_bundle.py and the SW-side verify contract.

We exercise the Python signer's output against the same Web Crypto
ECDSA-P256-SHA256 path the service worker uses: raw 64-byte r||s
signature, no DER. If the signer drifts (e.g. switches to DER output),
the verify side will silently reject and every fellow's SW install
will start failing. These tests are the bulwark against that.
"""
from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import sign_bundle  # noqa: E402


@pytest.fixture
def dev_key_pair() -> tuple[ec.EllipticCurvePrivateKey, bytes]:
    """Load the committed dev signing keypair (private + raw pub bytes)."""
    priv = serialization.load_pem_private_key(
        (REPO_ROOT / "tests" / "fixtures" / "dev_signing_key.pem").read_bytes(),
        password=None,
    )
    pub_hex = (REPO_ROOT / "tests" / "fixtures" / "dev_signing_key_pub.hex").read_text().strip()
    return priv, bytes.fromhex(pub_hex)


def _verify_raw_sig(pub_raw: bytes, manifest: bytes, raw_sig_64: bytes) -> bool:
    """Mirror what the SW does: take a 64-byte r||s signature and a
    raw uncompressed P-256 point, verify against the manifest."""
    if len(raw_sig_64) != 64:
        return False
    r = int.from_bytes(raw_sig_64[:32], "big")
    s = int.from_bytes(raw_sig_64[32:], "big")
    pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), pub_raw)
    try:
        pub.verify(encode_dss_signature(r, s), manifest, ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False


def test_sign_manifest_produces_raw_64_byte_signature(dev_key_pair):
    """`sign_manifest` MUST return raw 64-byte r||s, not DER. The SW's
    `crypto.subtle.verify({name:"ECDSA",hash:"SHA-256"}, ...)` rejects
    DER-formatted signatures with an opaque InvalidAccessError; this
    test pins the format so a future ‘cleanup’ that re-introduces DER
    output fails loud rather than silently bricking every install."""
    priv, _pub = dev_key_pair
    manifest = b'{"version":1,"files":{"app.js":"sha384-abc"}}'
    sig = sign_bundle.sign_manifest(priv, manifest)
    assert isinstance(sig, bytes)
    assert len(sig) == 64, f"expected raw 64-byte signature, got {len(sig)} bytes"


def test_sign_verify_roundtrip_matches_dev_pubkey(dev_key_pair):
    """End-to-end: sign a manifest, verify the signature against the
    committed dev public key the way the SW does. Same algorithm, same
    encoding, same key — must verify."""
    priv, pub_raw = dev_key_pair
    manifest = b'{"version":1,"alg":"ECDSA-P256-SHA256","files":{}}\n'
    raw_sig = sign_bundle.sign_manifest(priv, manifest)
    assert _verify_raw_sig(pub_raw, manifest, raw_sig)


def test_signature_fails_on_tampered_manifest(dev_key_pair):
    """Modifying a single byte of the manifest invalidates the
    signature — the property the whole feature rests on."""
    priv, pub_raw = dev_key_pair
    original = b'{"version":1,"files":{"app.js":"sha384-abc"}}'
    tampered = b'{"version":1,"files":{"app.js":"sha384-xyz"}}'
    raw_sig = sign_bundle.sign_manifest(priv, original)
    assert _verify_raw_sig(pub_raw, original, raw_sig)
    assert not _verify_raw_sig(pub_raw, tampered, raw_sig)


def test_signature_does_not_verify_against_other_key(dev_key_pair, tmp_path):
    """A signature from key A must not verify under key B — the
    property that prevents anyone-with-write-access to dist/ from
    signing arbitrary bundles unless they also hold the maintainer's
    private key."""
    priv_a, _ = dev_key_pair
    priv_b = ec.generate_private_key(ec.SECP256R1())
    pub_b = priv_b.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    manifest = b'whatever bytes'
    raw_sig = sign_bundle.sign_manifest(priv_a, manifest)
    assert not _verify_raw_sig(pub_b, manifest, raw_sig)


def test_script_writes_base64_signature_file(tmp_path, dev_key_pair):
    """Drive the script end-to-end: write a manifest, sign via the CLI,
    confirm the output file is base64 of a 64-byte signature and that
    it verifies against the committed dev pubkey."""
    _priv, pub_raw = dev_key_pair
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(b'{"version":1,"files":{}}\n')
    sig_path = tmp_path / "manifest.sig"

    rc = sign_bundle.main(
        [
            "--manifest",
            str(manifest_path),
            "--key",
            str(REPO_ROOT / "tests" / "fixtures" / "dev_signing_key.pem"),
            "--out",
            str(sig_path),
        ]
    )
    assert rc == 0
    assert sig_path.is_file()

    sig_b64 = sig_path.read_text().strip()
    raw = base64.b64decode(sig_b64)
    assert len(raw) == 64
    assert _verify_raw_sig(pub_raw, manifest_path.read_bytes(), raw)


def test_load_private_key_rejects_non_p256(tmp_path):
    """A non-P-256 EC key (e.g. P-384) fails loudly at load time —
    don't let a maintainer accidentally generate the wrong curve and
    discover the SW can't import their key only after a deploy."""
    priv = ec.generate_private_key(ec.SECP384R1())
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    bad_key = tmp_path / "wrong-curve.pem"
    bad_key.write_bytes(pem)
    with pytest.raises(SystemExit, match="P-256"):
        sign_bundle.load_private_key(bad_key, passphrase_env=None)
