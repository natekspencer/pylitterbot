#!/usr/bin/env python3
"""Helper to manage Whisker credentials securely."""

import configparser
import getpass
import os
from pathlib import Path


CREDS_FILE = Path(__file__).parent / ".whisker_credentials"


def load_credentials():
    """Load credentials from file."""
    if not CREDS_FILE.exists():
        return None, None

    # Disable interpolation to handle special characters like % correctly
    config = configparser.ConfigParser(interpolation=None)
    config.read(CREDS_FILE)

    try:
        email = config.get("whisker", "email")
        password = config.get("whisker", "password")

        if password == "YOUR_PASSWORD_HERE":
            print(f"⚠️  Password not set in {CREDS_FILE}")
            return email, None

        return email, password
    except (configparser.NoSectionError, configparser.NoOptionError):
        return None, None


def save_credentials(email, password):
    """Save credentials to file."""
    # Disable interpolation to handle special characters like % correctly
    config = configparser.ConfigParser(interpolation=None)
    config["whisker"] = {
        "email": email,
        "password": password,
    }

    with open(CREDS_FILE, "w") as f:
        f.write("# Whisker API Credentials for Testing\n")
        f.write("# WARNING: Keep this file secure! Never commit to git!\n\n")
        config.write(f)

    # Ensure secure permissions
    os.chmod(CREDS_FILE, 0o600)
    print(f"✓ Credentials saved to {CREDS_FILE}")
    print(f"✓ File permissions set to 600 (owner read/write only)")


def setup_credentials():
    """Interactive setup of credentials."""
    print("=" * 60)
    print("Whisker Credentials Setup")
    print("=" * 60)

    email = input("Whisker account email: ")
    password = getpass.getpass("Whisker account password: ")
    confirm = getpass.getpass("Confirm password: ")

    if password != confirm:
        print("❌ Passwords don't match!")
        return False

    save_credentials(email, password)
    return True


def get_credentials():
    """Get credentials, prompting if needed."""
    email, password = load_credentials()

    if email and password:
        return email, password

    print("⚠️  Credentials not found or incomplete.")
    print(f"Please run: python credentials_helper.py")
    return None, None


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        email, password = get_credentials()
        if email and password:
            print(f"✓ Email: {email}")
            print(f"✓ Password: {'*' * len(password)}")
        else:
            print("❌ No valid credentials found")
    else:
        setup_credentials()
