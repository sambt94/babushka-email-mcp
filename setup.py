# ABOUTME: One-time setup script for Babushka God Mode.
# ABOUTME: Walks users through connecting email accounts and saves config.json.

import getpass
import json
from pathlib import Path

APP_PASSWORD_HELP = {
    "icloud": """
  How to get your iCloud app-specific password:
  1. Go to https://appleid.apple.com
  2. Sign in → Sign-In and Security → App-Specific Passwords
  3. Click "Generate an app-specific password"
  4. Name it "Babushka" and copy the password (format: xxxx-xxxx-xxxx-xxxx)
""",
    "gmail": """
  How to get your Gmail app password:
  1. You need 2-Step Verification enabled on your Google account
  2. Go to https://myaccount.google.com/apppasswords
  3. Create an app password, name it "Babushka"
  4. Copy the 16-character password (format: xxxx xxxx xxxx xxxx)
""",
    "outlook": """
  How to get your Outlook app password:
  1. Go to https://account.microsoft.com
  2. Security → Advanced security options
  3. Under "App passwords", create a new one
  4. Copy the generated password
""",
}

SERVER_DIR = Path(__file__).parent.resolve()


def add_account():
    """Prompt user for one account's details and return a dict."""
    print()
    print("Which email provider?")
    print("  1. iCloud")
    print("  2. Gmail")
    print("  3. Outlook")
    choice = input("Enter 1, 2, or 3: ").strip()

    providers = {"1": "icloud", "2": "gmail", "3": "outlook"}
    provider = providers.get(choice, "icloud")
    default_name = provider.capitalize()

    # Show app password instructions
    print(APP_PASSWORD_HELP.get(provider, ""))

    name = input(f"Account name [{default_name}]: ").strip() or default_name
    email_addr = input(f"Your {provider} email address: ").strip()
    password = getpass.getpass("App-specific password (paste it here): ").strip()

    return {
        "name": name,
        "provider": provider,
        "email": email_addr,
        "password": password,
    }


def setup():
    print()
    print("👵 Babushka God Mode Setup")
    print("=" * 40)
    print()
    print("I'll help you connect your email accounts, dear.")
    print("You'll need an app-specific password for each one")
    print("(your normal login won't work with IMAP).")

    config_path = Path(__file__).parent / "config.json"

    # Load existing accounts if present
    existing_accounts = []
    if config_path.exists():
        try:
            with open(config_path) as f:
                existing = json.load(f)
            if "accounts" in existing:
                existing_accounts = existing["accounts"]
            elif "email" in existing:
                acc = dict(existing)
                acc.setdefault("name", existing.get("provider", "default").capitalize())
                existing_accounts = [acc]
            if existing_accounts:
                print()
                print(f"Found {len(existing_accounts)} existing account(s):")
                for acc in existing_accounts:
                    print(f"  ✓ {acc.get('name', '?')} ({acc.get('email', '?')})")
        except (json.JSONDecodeError, IOError):
            pass

    accounts = list(existing_accounts)

    # Add accounts in a loop
    while True:
        if accounts:
            print()
            add_more = input("Add another account? (y/n): ").strip().lower()
            if add_more != "y":
                break

        account = add_account()
        accounts.append(account)
        print(f"\n  ✅ Added {account['name']} ({account['email']})")

    if not accounts:
        print("\nNo accounts configured. Run this again when you're ready, dear.")
        return

    # Separate passwords from config — passwords go in MCP env, not on disk
    passwords = {}
    config_accounts = []
    for acc in accounts:
        env_key = f"BABUSHKA_{acc['name'].upper().replace(' ', '_')}_PASSWORD"
        passwords[env_key] = acc["password"]
        config_accounts.append({
            "name": acc["name"],
            "provider": acc["provider"],
            "email": acc["email"],
        })

    config = {"accounts": config_accounts}
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print()
    print("=" * 40)
    print(f"✅ Saved {len(accounts)} account(s) to config.json (no passwords stored)")
    print()
    print("Next: Add the MCP server to Claude Code.")
    print()
    print("Add this to ~/.claude/.mcp.json (global) or")
    print("~/Library/Application Support/Claude/claude_desktop_config.json (Desktop):")
    print()
    mcp_config = {
        "mcpServers": {
            "babushka": {
                "command": "uv",
                "args": ["run", "--directory", str(SERVER_DIR), "python", "server.py"],
                "env": passwords,
            }
        }
    }
    print(json.dumps(mcp_config, indent=2))
    print()
    print("Your passwords are passed as environment variables, not stored in config.json.")
    print()
    print("Then open Claude Code and say: \"scan my inbox\"")
    print()
    print("👵 Babushka is ready to protect your inbox, dear!")


if __name__ == "__main__":
    setup()
