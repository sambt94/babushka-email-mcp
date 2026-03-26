# Babushka Email MCP

Full inbox management through Claude Code. Babushka reads your emails, catches phishing, and cleans up your inbox — with your permission.

## What You Need

- [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (CLI)
- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- An email account with IMAP access (iCloud, Gmail, or Outlook)

## Setup

### 1. Clone and install

```bash
git clone https://github.com/sambt94/babushka-email-mcp.git
cd babushka-email-mcp
uv sync
```

### 2. Get an app-specific password for your email

You need an app-specific password — your normal login won't work with IMAP.

**iCloud:**
1. Go to [appleid.apple.com](https://appleid.apple.com) → Sign-In and Security → App-Specific Passwords
2. Click "Generate an app-specific password"
3. Name it "Babushka" and copy the password (format: `xxxx-xxxx-xxxx-xxxx`)

**Gmail:**
1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. You need 2FA enabled on your Google account
3. Create an app password, name it "Babushka" and copy it

**Outlook:**
1. Go to [account.microsoft.com](https://account.microsoft.com) → Security → Advanced security options
2. Under "App passwords", create a new one

### 3. Configure your credentials

Run the setup script:

```bash
uv run python setup.py
```

This creates a `config.json` with your account details (no passwords stored on disk) and outputs the MCP configuration with your passwords as environment variables.

Or set it up manually:

**a) Create `config.json`** (account info only, no passwords):

```json
{
  "accounts": [
    {
      "name": "iCloud",
      "provider": "icloud",
      "email": "your@icloud.com"
    },
    {
      "name": "Gmail",
      "provider": "gmail",
      "email": "your@gmail.com"
    }
  ]
}
```

Provider options: `icloud`, `gmail`, `outlook`. You can add as many accounts as you like.

**b) Add the MCP server** to `~/.claude/.mcp.json` (global) or your project's `.mcp.json`:

```json
{
  "mcpServers": {
    "babushka": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/babushka-email-mcp", "python", "server.py"],
      "env": {
        "BABUSHKA_ICLOUD_PASSWORD": "xxxx-xxxx-xxxx-xxxx",
        "BABUSHKA_GMAIL_PASSWORD": "xxxx xxxx xxxx xxxx"
      }
    }
  }
}
```

Passwords are passed as environment variables (`BABUSHKA_<ACCOUNT_NAME>_PASSWORD`), not stored in config.json. The env var name is derived from your account name — e.g., an account named "Work Gmail" becomes `BABUSHKA_WORK_GMAIL_PASSWORD`.

For **Claude Desktop**, add the same to `~/Library/Application Support/Claude/claude_desktop_config.json`.

### 5. Open Claude Code and go

```bash
cd babushka-god-mode
claude
```

Then just say: **"scan my inbox"**

## What It Does

- Scans your inbox for phishing, spam, and junk
- Catches sender domain mismatches (the #1 phishing signal)
- Categorises everything: important, newsletters, marketing, suspicious, phishing
- Asks before taking any action — never moves or deletes without permission
- Follows YOUR rules in `babushka-rules.md`

## Available Tools

| Tool | What it does |
|------|-------------|
| `babushka_list_accounts` | List all configured email accounts |
| `babushka_list_emails` | List recent emails from any folder |
| `babushka_read_email` | Read full email content |
| `babushka_archive_email` | Move email to Archive |
| `babushka_junk_email` | Move email to Junk/Spam |
| `babushka_trash_email` | Move email to Trash |
| `babushka_move_email` | Move email to any folder |
| `babushka_list_folders` | List all available folders |
| `babushka_send_email` | Send an email (replies, summaries) |
| `babushka_read_email_html` | Read HTML body, find unsubscribe links |
| `babushka_create_folder` | Create a new email folder |

## Skills

Babushka has 6 built-in skills. Just say the trigger phrase and she'll guide you through it.

| Skill | What it does | Try saying |
|-------|-------------|------------|
| Setup Wizard | Generates your personal `babushka-rules.md` through a guided Q&A | "set up my rules" |
| Daily Briefing | Scans overnight emails, categorises, summarises what matters | "what's important today?" |
| Quick Reply | Drafts and sends replies with your approval | "reply to that email from Manav" |
| Unsubscribe Sweep | Finds frequent marketing senders and their unsubscribe links | "unsubscribe sweep" |
| Folder Organiser | Suggests folders based on your email patterns, creates and sorts | "organise my folders" |
| Learn My Patterns | Watches what you archive/junk and suggests rule updates | "update my rules" |

## Customise Your Rules

Edit `babushka-rules.md` to:
- Add trusted senders (never flagged)
- Change spam aggressiveness
- Set category actions (archive marketing, keep newsletters, etc.)
- Adjust what gets archived vs kept

## Multi-Account Support

Babushka manages all your inboxes simultaneously. Add multiple accounts to `config.json` and she'll scan them all. Target a specific account by saying "check my Gmail" or "scan my iCloud".

## Example Session

```
You: scan my inbox
Babushka: Let me take a look, dear...

🔴 PHISHING (2 emails)
- "DPD Delivery" <notify@parcel-track.xyz> — NOT the real DPD
- "British Gas" <billing@energy-alert.jp> — NOT British Gas

📦 MARKETING (5 emails)
- Fastic — "$89 voucher" pressure tactics
- Raffle House — lottery upsell

✅ IMPORTANT (3 emails)
- Apple — app-specific password created
- Mum — dinner plans

👵 Shall I junk the 2 phishing emails and archive the marketing?

You: yes please
Babushka: Done! Your inbox is looking much tidier now, dear.
```
