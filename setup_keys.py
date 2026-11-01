"""Generate a dev ES256 keypair. keys/ is gitignored — never commit real keys."""
import os

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

KEY_DIR = os.path.join(os.path.dirname(__file__), "keys")
os.makedirs(KEY_DIR, exist_ok=True)

private_key = ec.generate_private_key(ec.SECP256R1())
public_key = private_key.public_key()

with open(os.path.join(KEY_DIR, "es256-private.pem"), "wb") as f:
    f.write(
        private_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
with open(os.path.join(KEY_DIR, "es256-public.pem"), "wb") as f:
    f.write(
        public_key.public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
print("dev ES256 keypair written to", KEY_DIR)
