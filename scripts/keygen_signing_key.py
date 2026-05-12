#!/usr/bin/env python3
"""Generate the prod ECDSA P-256 signing keypair for the bundle-signature
flow. One-time per maintainer; the resulting key is what the dev's
``just sign`` and ``just ship`` use to sign every release.

Usage:
    python scripts/keygen_signing_key.py [--out PATH] [--no-passphrase]

By default the private key is written to ``~/.fellows/signing-key.enc.pem``
(0600), encrypted with a passphrase that the operator types twice at the
prompt. The public key is printed to stdout in two forms:

  1. Hex-encoded uncompressed point (130 hex chars) — paste this into
     ``app/static/sw.js``'s ``PROD_PUBLIC_KEY_HEX`` constant and commit.
  2. SHA-384 fingerprint — also computed and printed for reference; the
     build pipeline derives the same value automatically from sw.js so
     it doesn't need to be committed anywhere.

After running this once, the next ``just ship`` will sign the bundle
with the new key. See ``docs/DevOps.md`` § Signing keys and bundle
verification for the full workflow and the backup checklist.

This script never writes the unencrypted private key to disk. The
passphrase is read interactively so it never lands in shell history.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


DEFAULT_KEY_PATH = Path.home() / ".fellows" / "signing-key.enc.pem"


def generate_keypair():
    """Return (private_key, public_key_raw_bytes). Raw is the
    uncompressed-point form (0x04 || X || Y) that Web Crypto's
    importKey accepts directly with ``format: "raw"``."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    raw_pub = public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return private_key, raw_pub


def read_passphrase(no_passphrase: bool) -> bytes | None:
    if no_passphrase:
        return None
    while True:
        p1 = getpass.getpass("Passphrase (used to encrypt the private key): ")
        if not p1:
            print("Passphrase cannot be empty. Try again, or pass --no-passphrase.")
            continue
        p2 = getpass.getpass("Confirm passphrase: ")
        if p1 != p2:
            print("Passphrases do not match. Try again.")
            continue
        return p1.encode("utf-8")


def write_private_key(private_key, out_path: Path, passphrase: bytes | None) -> None:
    if passphrase is not None:
        encryption: serialization.KeySerializationEncryption = (
            serialization.BestAvailableEncryption(passphrase)
        )
    else:
        encryption = serialization.NoEncryption()
    pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=encryption,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Write with mode 0600 — no group/other access ever. umask doesn't
    # apply because we set the mode explicitly.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(str(out_path), flags, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(pem)
    except Exception:
        try:
            out_path.unlink()
        except OSError:
            pass
        raise


def fingerprint_for_pubkey(raw_pub: bytes) -> str:
    """SHA-384 hex of the raw public key bytes. Same algorithm
    ``build/build_pwa.py:compute_pubkey_fingerprint`` uses, so the
    operator's printout and the served fingerprint stay in lockstep."""
    return hashlib.sha384(raw_pub).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_KEY_PATH,
        help=f"Where to write the encrypted private key (default: {DEFAULT_KEY_PATH})",
    )
    parser.add_argument(
        "--no-passphrase",
        action="store_true",
        help="Generate an unencrypted private key. ONLY for test fixtures.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing key file. Default refuses to clobber.",
    )
    args = parser.parse_args(argv)

    if args.out.exists() and not args.force:
        print(
            f"Refusing to overwrite existing key at {args.out}. "
            f"Pass --force if you really mean to.",
            file=sys.stderr,
        )
        return 1

    private_key, raw_pub = generate_keypair()
    passphrase = read_passphrase(args.no_passphrase)
    write_private_key(private_key, args.out, passphrase)

    pubkey_hex = raw_pub.hex()
    fp = fingerprint_for_pubkey(raw_pub)

    print()
    print(f"Wrote encrypted private key: {args.out}")
    print()
    print("Public key (raw uncompressed point, hex — 130 chars):")
    print(f"  {pubkey_hex}")
    print()
    print("SHA-384 fingerprint of the public key:")
    print(f"  {fp}")
    print()
    print("Next steps:")
    print(
        "  1. Open app/static/sw.js and replace the PROD_PUBLIC_KEY_HEX"
        " constant with the hex string above. Commit."
    )
    print(
        "  2. Back up the encrypted private key file to at least two"
        " off-laptop locations (USB + cloud, or USB + paper QR)."
    )
    print(
        "  3. Verify backups by attempting `python scripts/sign_bundle.py"
        " --dry-run --key <backup-path>` on a fresh machine."
    )
    print(
        "  4. On your next `just ship`, the build will sign the bundle"
        " with this key."
    )
    print()
    print(
        "If you ever lose this key, you cannot push further updates."
        " Users keep running the last version they verified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
