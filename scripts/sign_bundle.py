#!/usr/bin/env python3
"""Sign ``deploy/dist/manifest.json`` with the maintainer's ECDSA P-256
private key. Output goes to ``deploy/dist/manifest.sig`` as a base64-
encoded raw 64-byte (r||s) signature — the form Web Crypto's
``crypto.subtle.verify({name:"ECDSA",hash:"SHA-256"}, ...)`` expects.

Usage:
    python scripts/sign_bundle.py [--manifest PATH] [--key PATH]
                                  [--out PATH] [--passphrase-env VAR]

Defaults:
    --manifest    deploy/dist/manifest.json
    --key         ~/.fellows/signing-key.enc.pem  (set by keygen_signing_key.py)
    --out         <manifest>.sig
    --passphrase  read interactively unless --passphrase-env is set

The dev server has its own signing path that uses the committed test
keypair under ``tests/fixtures/``; this script is the *prod* signer.

Why we convert the signature: ``cryptography.hazmat`` emits ECDSA
signatures in DER (ASN.1) form by default. Web Crypto wants raw
``r || s``, each 32 bytes for P-256. The conversion is exact and
information-preserving — DER carries r and s as INTEGERs (with
variable length and a sign bit), the raw form fixes them at 32 bytes
each.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import os
import sys
from pathlib import Path

from cryptography.exceptions import InvalidKey
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = REPO_ROOT / "deploy" / "dist" / "manifest.json"
DEFAULT_KEY = Path.home() / ".fellows" / "signing-key.enc.pem"


def load_private_key(key_path: Path, passphrase_env: str | None) -> ec.EllipticCurvePrivateKey:
    """Load an ECDSA P-256 private key from a PEM file. Encrypted keys
    prompt for a passphrase unless ``--passphrase-env`` points at an
    env var holding it (useful for CI; the operator's normal flow is
    the interactive prompt)."""
    if not key_path.is_file():
        raise SystemExit(f"key not found: {key_path}")

    raw = key_path.read_bytes()

    # First attempt: unencrypted. If that fails, prompt for passphrase.
    try:
        key = serialization.load_pem_private_key(raw, password=None)
    except TypeError:
        # PEM is encrypted; need a passphrase.
        if passphrase_env:
            pw = os.environ.get(passphrase_env, "")
            if not pw:
                raise SystemExit(
                    f"Encrypted key but {passphrase_env} is unset/empty."
                )
            try:
                key = serialization.load_pem_private_key(raw, password=pw.encode("utf-8"))
            except (ValueError, InvalidKey) as e:
                raise SystemExit(f"Failed to decrypt key with {passphrase_env}: {e}")
        else:
            for _ in range(3):
                pw = getpass.getpass(f"Passphrase for {key_path}: ").encode("utf-8")
                try:
                    key = serialization.load_pem_private_key(raw, password=pw)
                    break
                except (ValueError, InvalidKey):
                    print("Wrong passphrase. Try again.", file=sys.stderr)
            else:
                raise SystemExit("Too many failed passphrase attempts.")

    if not isinstance(key, ec.EllipticCurvePrivateKey):
        raise SystemExit(f"key is not an EC private key: {type(key).__name__}")
    if not isinstance(key.curve, ec.SECP256R1):
        raise SystemExit(f"key is not P-256: curve={key.curve.name}")
    return key


def sign_manifest(private_key: ec.EllipticCurvePrivateKey, manifest_bytes: bytes) -> bytes:
    """Sign manifest bytes with ECDSA-P256-SHA256, return raw 64-byte
    r||s signature (Web Crypto's format). Caller usually base64-encodes
    before writing."""
    der_sig = private_key.sign(manifest_bytes, ec.ECDSA(hashes.SHA256()))
    r, s = decode_dss_signature(der_sig)
    raw = r.to_bytes(32, "big") + s.to_bytes(32, "big")
    return raw


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--key", type=Path, default=DEFAULT_KEY)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output signature path. Default: <manifest>.sig",
    )
    parser.add_argument(
        "--passphrase-env",
        default=None,
        help="Env var holding the key passphrase (skips interactive prompt).",
    )
    args = parser.parse_args(argv)

    if not args.manifest.is_file():
        print(f"manifest not found: {args.manifest}", file=sys.stderr)
        print("Run `just build` first.", file=sys.stderr)
        return 1
    out_path = args.out if args.out else args.manifest.with_suffix(".sig")

    private_key = load_private_key(args.key, args.passphrase_env)
    manifest_bytes = args.manifest.read_bytes()
    raw_sig = sign_manifest(private_key, manifest_bytes)
    b64 = base64.b64encode(raw_sig).decode("ascii")
    out_path.write_text(b64 + "\n", encoding="utf-8")
    out_path.chmod(0o644)

    print(f"Wrote {out_path} ({len(b64)} base64 chars; raw {len(raw_sig)} bytes).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
