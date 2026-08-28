import sqlite3
import hashlib
import secrets
from pathlib import Path

db_file = Path("/home/huy/CCH_Network/logs/auth.sqlite3")
if not db_file.exists():
    print(f"File {db_file} does not exist!")
    exit(1)

conn = sqlite3.connect(db_file)
conn.row_factory = sqlite3.Row

users = conn.execute("SELECT id, username, role, failed_attempts, locked_until, disabled, password_hash FROM users").fetchall()
print("CURRENT USERS IN DB:")
for u in users:
    print(f"  User: {u['username']}, Role: {u['role']}, Failed: {u['failed_attempts']}, Locked: {u['locked_until']}, Disabled: {u['disabled']}")

# Reset admin password to CCH@1234
salt = secrets.token_bytes(16)
digest = hashlib.pbkdf2_hmac("sha256", "CCH@1234".encode("utf-8"), salt, 600_000)
new_hash = f"pbkdf2_sha256$600000${salt.hex()}${digest.hex()}"

conn.execute(
    "UPDATE users SET password_hash = ?, failed_attempts = 0, locked_until = NULL, disabled = 0 WHERE username = 'admin'",
    (new_hash,)
)
conn.commit()

# Verify
admin = conn.execute("SELECT * FROM users WHERE username = 'admin'").fetchone()
if admin:
    print("\nADMIN USER UPDATED SUCCESSFULLY:")
    print(f"  Username: {admin['username']}")
    print(f"  Failed attempts: {admin['failed_attempts']}")
    print(f"  Locked until: {admin['locked_until']}")
    print(f"  Disabled: {admin['disabled']}")
    
    # Test verify
    algo, rounds, s_hex, d_hex = admin['password_hash'].split('$', 3)
    test_dig = hashlib.pbkdf2_hmac("sha256", "CCH@1234".encode("utf-8"), bytes.fromhex(s_hex), int(rounds))
    if test_dig.hex() == d_hex:
        print("  Password verification for 'CCH@1234': MATCH (SUCCESS!)")
    else:
        print("  Password verification: FAILED")
else:
    print("Admin user not found!")

conn.close()
