"""Verify the pinned public Tokyo RDS trust bundle without AWS access."""
import hashlib
import ssl
import subprocess
import tempfile
import time
from pathlib import Path
from typing import cast


def main() -> None:
    certs = Path(__file__).resolve().parents[1] / "certs"
    bundle = certs / "rds-ap-northeast-1-bundle.pem"
    expected, filename = (certs / "SHA256SUMS").read_text().strip().split()
    assert filename == bundle.name
    contents = bundle.read_bytes()
    assert b"PRIVATE KEY" not in contents
    assert hashlib.sha256(contents).hexdigest() == expected
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.load_verify_locations(cafile=str(bundle))
    certificates = context.get_ca_certs()
    assert certificates and len(certificates) == contents.count(b"-----BEGIN CERTIFICATE-----")
    names: list[str] = []
    for cert in certificates:
        assert cert["subject"] == cert["issuer"], "Bundle must contain only self-issued roots"
        not_before, not_after = cert["notBefore"], cert["notAfter"]
        assert isinstance(not_before, str) and isinstance(not_after, str)
        assert ssl.cert_time_to_seconds(not_before) <= time.time()
        assert ssl.cert_time_to_seconds(not_after) > time.time()
        # ssl documents subject as a tuple of RDN tuples of (attribute, value).
        subject = cast(tuple[tuple[tuple[str, str], ...], ...], cert["subject"])
        names.extend(value for rdn in subject for key, value in rdn if key == "commonName")
    assert "Amazon RDS ap-northeast-1 Root CA RSA2048 G1" in names
    with tempfile.TemporaryDirectory(prefix="fitlog-ca-") as folder:
        for index, der in enumerate(context.get_ca_certs(binary_form=True)):
            root = Path(folder) / f"root-{index}.pem"
            root.write_text(ssl.DER_cert_to_PEM_cert(der))
            subprocess.run(["openssl", "verify", "-check_ss_sig", "-CAfile", str(root), str(root)],
                           check=True, capture_output=True, text=True, timeout=10)
    print("RDS CA: pinned hash, PEM, CA roots, validity, Tokyo RSA2048 G1, self-signatures: OK")


if __name__ == "__main__":
    main()
