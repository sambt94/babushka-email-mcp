# ABOUTME: Babushka God Mode MCP server — full email read/write via IMAP.
# ABOUTME: Supports multiple accounts (iCloud, Gmail, Outlook) simultaneously.

import json
import os
import re
import imaplib
import email
import smtplib
from email.header import decode_header
from email.mime.text import MIMEText
from email.utils import parseaddr
from pathlib import Path

# Enable IMAP MOVE extension (RFC 6851)
imaplib.Commands['MOVE'] = ('SELECTED',)

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Load instructions from CLAUDE.md + babushka-rules.md so any MCP client
# (Claude Desktop, Claude Code, etc.) gets the full Babushka personality.
_INSTRUCTIONS_DIR = Path(__file__).parent
_instructions_parts = []
for fname in ["CLAUDE.md", "babushka-rules.md"]:
    fpath = _INSTRUCTIONS_DIR / fname
    if fpath.exists():
        _instructions_parts.append(fpath.read_text())
BABUSHKA_INSTRUCTIONS = "\n\n---\n\n".join(_instructions_parts) if _instructions_parts else None

app = Server("babushka-god-mode", instructions=BABUSHKA_INSTRUCTIONS)

# Load credentials from config file
CONFIG_PATH = Path(__file__).parent / "config.json"

# Account parameter added to all tools that need a connection
ACCOUNT_PARAM = {
    "account": {
        "type": "string",
        "description": "Account name (from babushka_list_accounts). Defaults to first account.",
        "default": "",
    }
}

FROM_FOLDER_PARAM = {
    "from_folder": {
        "type": "string",
        "description": "Source folder (defaults to INBOX).",
        "default": "INBOX",
    }
}


def get_config():
    if not CONFIG_PATH.exists():
        return None
    with open(CONFIG_PATH) as f:
        return json.load(f)


def get_accounts(config):
    """Return a list of account dicts from config. Supports both old and new format."""
    if config is None:
        return []
    # New multi-account format
    if "accounts" in config:
        return config["accounts"]
    # Old single-account format — wrap in a list
    if "email" in config:
        account = dict(config)
        account.setdefault("name", config.get("provider", "default").capitalize())
        return [account]
    return []


def _get_password(account):
    """Get password from env var (preferred) or config.json fallback."""
    # Env var convention: BABUSHKA_<NAME>_PASSWORD (e.g. BABUSHKA_ICLOUD_PASSWORD)
    name = account.get("name", account.get("provider", "default"))
    env_key = f"BABUSHKA_{name.upper().replace(' ', '_')}_PASSWORD"
    return os.environ.get(env_key) or account.get("password", "")


def resolve_account(config, account_name=""):
    """Resolve an account by name, provider, or default to first."""
    accounts = get_accounts(config)
    if not accounts:
        return None
    if not account_name:
        acc = accounts[0]
    else:
        acc = None
        # Exact name match (case-insensitive)
        for a in accounts:
            if a.get("name", "").lower() == account_name.lower():
                acc = a
                break
        # Fuzzy match on provider
        if acc is None:
            for a in accounts:
                if a.get("provider", "").lower() == account_name.lower():
                    acc = a
                    break
        if acc is None:
            acc = accounts[0]
    # Inject password from env var if available
    acc["password"] = _get_password(acc)
    return acc


def get_imap_connection(account):
    provider = account.get("provider", "icloud")
    servers = {
        "icloud": "imap.mail.me.com",
        "gmail": "imap.gmail.com",
        "outlook": "outlook.office365.com",
    }
    host = servers.get(provider, account.get("imap_host", ""))
    conn = imaplib.IMAP4_SSL(host)
    conn.login(account["email"], account["password"])
    return conn


def get_smtp_connection(account):
    provider = account.get("provider", "icloud")
    servers = {
        "icloud": "smtp.mail.me.com",
        "gmail": "smtp.gmail.com",
        "outlook": "smtp.office365.com",
    }
    host = servers.get(provider, account.get("smtp_host", ""))
    smtp = smtplib.SMTP(host, 587)
    smtp.starttls()
    smtp.login(account["email"], account["password"])
    return smtp


def decode_subject(msg):
    subject = msg.get("Subject", "")
    decoded_parts = decode_header(subject)
    result = ""
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            result += part.decode(charset or "utf-8", errors="replace")
        else:
            result += part
    return result


def get_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")[:4000]
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode("utf-8", errors="replace")[:4000]
    return ""


def get_html_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode("utf-8", errors="replace")[:8000]
    else:
        if msg.get_content_type() == "text/html":
            payload = msg.get_payload(decode=True)
            if payload:
                return payload.decode("utf-8", errors="replace")[:8000]
    return ""


def _props(*extra_dicts):
    """Merge property dicts together with the account param."""
    merged = {}
    for d in extra_dicts:
        merged.update(d)
    merged.update(ACCOUNT_PARAM)
    return merged


# Provider-specific folder names for archive, junk, and trash
FOLDER_MAP = {
    "icloud": {"archive": "Archive", "junk": "Junk", "trash": "Trash"},
    "gmail": {"archive": "[Gmail]/All Mail", "junk": "[Gmail]/Spam", "trash": "[Gmail]/Trash"},
    "outlook": {"archive": "Archive", "junk": "Junk", "trash": "Deleted Items"},
}


def get_folder(account, role):
    """Get the correct folder name for a given role (archive/junk/trash) based on provider."""
    provider = account.get("provider", "icloud")
    return FOLDER_MAP.get(provider, FOLDER_MAP["icloud"])[role]


def _imap_folder(name):
    """Quote an IMAP folder name if it contains special characters or non-ASCII."""
    if any(c in name for c in ' []/') or not name.isascii():
        return f'"{name}"'
    return name


@app.list_tools()
async def list_tools():
    return [
        Tool(
            name="babushka_list_accounts",
            description="List all configured email accounts. Returns account names and providers (no passwords).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="babushka_list_emails",
            description="List emails from the inbox. Returns sender, subject, date, and UID for each email.",
            inputSchema={
                "type": "object",
                "properties": _props({
                    "folder": {"type": "string", "description": "Folder to list from", "default": "INBOX"},
                    "limit": {"type": "integer", "description": "Max emails to return", "default": 20},
                }),
            },
        ),
        Tool(
            name="babushka_read_email",
            description="Read a full email by its UID. Returns sender, subject, date, and body text.",
            inputSchema={
                "type": "object",
                "properties": _props({
                    "uid": {"type": "string", "description": "Email UID from babushka_list_emails"},
                    "folder": {"type": "string", "description": "Folder the email is in", "default": "INBOX"},
                }),
                "required": ["uid"],
            },
        ),
        Tool(
            name="babushka_read_email_html",
            description="Read email HTML body. Use to find unsubscribe links, tracking pixels, or formatted content.",
            inputSchema={
                "type": "object",
                "properties": _props({
                    "uid": {"type": "string", "description": "Email UID"},
                    "folder": {"type": "string", "description": "Folder the email is in", "default": "INBOX"},
                }),
                "required": ["uid"],
            },
        ),
        Tool(
            name="babushka_archive_email",
            description="Archive an email by moving it to the Archive folder.",
            inputSchema={
                "type": "object",
                "properties": _props(FROM_FOLDER_PARAM, {
                    "uid": {"type": "string", "description": "Email UID to archive"},
                }),
                "required": ["uid"],
            },
        ),
        Tool(
            name="babushka_junk_email",
            description="Move an email to the Junk/Spam folder.",
            inputSchema={
                "type": "object",
                "properties": _props(FROM_FOLDER_PARAM, {
                    "uid": {"type": "string", "description": "Email UID to junk"},
                }),
                "required": ["uid"],
            },
        ),
        Tool(
            name="babushka_trash_email",
            description="Move an email to the Trash folder.",
            inputSchema={
                "type": "object",
                "properties": _props(FROM_FOLDER_PARAM, {
                    "uid": {"type": "string", "description": "Email UID to trash"},
                }),
                "required": ["uid"],
            },
        ),
        Tool(
            name="babushka_move_email",
            description="Move an email to a specific folder.",
            inputSchema={
                "type": "object",
                "properties": _props(FROM_FOLDER_PARAM, {
                    "uid": {"type": "string", "description": "Email UID to move"},
                    "to_folder": {"type": "string", "description": "Destination folder name"},
                }),
                "required": ["uid", "to_folder"],
            },
        ),
        Tool(
            name="babushka_send_email",
            description="Send an email. Use for replies, forwarding summaries, or any outbound email.",
            inputSchema={
                "type": "object",
                "properties": _props({
                    "to": {"type": "string", "description": "Recipient email address"},
                    "subject": {"type": "string", "description": "Email subject line"},
                    "body": {"type": "string", "description": "Plain text email body"},
                }),
                "required": ["to", "subject", "body"],
            },
        ),
        Tool(
            name="babushka_create_folder",
            description="Create a new email folder/mailbox.",
            inputSchema={
                "type": "object",
                "properties": _props({
                    "folder_name": {"type": "string", "description": "Name for the new folder"},
                }),
                "required": ["folder_name"],
            },
        ),
        Tool(
            name="babushka_list_folders",
            description="List all available email folders/mailboxes.",
            inputSchema={
                "type": "object",
                "properties": _props({}),
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict):
    config = get_config()
    if not config:
        return [TextContent(type="text", text="No config.json found. Run: python setup.py")]

    # Handle list_accounts separately — no connection needed
    if name == "babushka_list_accounts":
        accounts = get_accounts(config)
        safe_accounts = []
        for acc in accounts:
            safe_accounts.append({
                "name": acc.get("name", ""),
                "provider": acc.get("provider", ""),
                "email": acc.get("email", ""),
            })
        return [TextContent(type="text", text=json.dumps(safe_accounts, indent=2))]

    # Resolve account for all other tools
    account = resolve_account(config, arguments.get("account", ""))
    if not account:
        return [TextContent(type="text", text="No accounts configured. Run: python setup.py")]

    account_label = account.get("name", account.get("provider", "default"))

    # Handle send_email separately — only needs SMTP, not IMAP
    if name == "babushka_send_email":
        to_addr = arguments["to"]
        subject = arguments["subject"]
        body = arguments["body"]
        msg = MIMEText(body)
        msg["From"] = account["email"]
        msg["To"] = to_addr
        msg["Subject"] = subject
        try:
            smtp = get_smtp_connection(account)
            smtp.send_message(msg)
            smtp.quit()
        except Exception as e:
            return [TextContent(type="text", text=f"Send failed ({account_label}): {e}")]
        return [TextContent(type="text", text=f"Sent email to {to_addr}: {subject} ({account_label})")]

    try:
        conn = get_imap_connection(account)
    except Exception as e:
        return [TextContent(type="text", text=f"Connection failed ({account_label}): {e}")]

    try:
        if name == "babushka_list_emails":
            folder = arguments.get("folder", "INBOX")
            limit = arguments.get("limit", 20)

            conn.select(folder, readonly=True)
            _, data = conn.uid("search", None, "ALL")
            uids = data[0].split()
            uids = uids[-limit:]  # Most recent
            uids.reverse()

            emails = []
            if uids:
                # Batch fetch all headers in one IMAP command
                uid_set = b",".join(uids)
                _, msg_data = conn.uid("fetch", uid_set, "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)])")
                # IMAP returns pairs: (header_bytes, body_bytes) followed by b')'
                uid_header_map = {}
                for i in range(0, len(msg_data)):
                    item = msg_data[i]
                    if not isinstance(item, tuple) or len(item) < 2:
                        continue
                    # Extract UID from the response line, e.g. b'5 (UID 123 BODY[...]'
                    meta = item[0]
                    uid_match = re.search(rb'UID\s+(\d+)', meta)
                    if uid_match:
                        uid_header_map[uid_match.group(1)] = item[1]

                for uid in uids:
                    raw = uid_header_map.get(uid)
                    if raw is None:
                        continue
                    msg = email.message_from_bytes(raw)
                    sender_name, sender_addr = parseaddr(msg.get("From", ""))
                    emails.append({
                        "uid": uid.decode(),
                        "from_name": sender_name,
                        "from_email": sender_addr,
                        "subject": decode_subject(msg),
                        "date": msg.get("Date", ""),
                        "account": account_label,
                    })

            return [TextContent(type="text", text=json.dumps(emails, indent=2))]

        elif name == "babushka_read_email":
            uid = arguments["uid"]
            folder = arguments.get("folder", "INBOX")

            conn.select(folder, readonly=True)
            _, msg_data = conn.uid("fetch", uid, "(RFC822)")
            if msg_data[0] is None:
                return [TextContent(type="text", text=f"Email not found ({account_label})")]

            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            sender_name, sender_addr = parseaddr(msg.get("From", ""))

            result = {
                "uid": arguments["uid"],
                "from_name": sender_name,
                "from_email": sender_addr,
                "subject": decode_subject(msg),
                "date": msg.get("Date", ""),
                "body": get_body(msg),
                "account": account_label,
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "babushka_read_email_html":
            uid = arguments["uid"]
            folder = arguments.get("folder", "INBOX")
            conn.select(folder, readonly=True)
            _, msg_data = conn.uid("fetch", uid, "(RFC822)")
            if msg_data[0] is None:
                return [TextContent(type="text", text=f"Email not found ({account_label})")]
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            html = get_html_body(msg)
            if not html:
                return [TextContent(type="text", text=f"No HTML body found in this email ({account_label})")]
            unsub_links = re.findall(r'href="([^"]*(?:unsubscribe|opt[._-]?out|remove)[^"]*)"', html, re.IGNORECASE)
            result = {
                "uid": uid,
                "html_preview": html[:4000],
                "unsubscribe_links": unsub_links,
                "account": account_label,
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "babushka_archive_email":
            uid = arguments["uid"]
            provider = account.get("provider", "icloud")
            conn.select(_imap_folder(arguments.get("from_folder", "INBOX")))
            if provider == "gmail":
                # Gmail doesn't support MOVE. Archive = COPY to All Mail + delete from INBOX.
                conn.uid("COPY", uid, _imap_folder("[Gmail]/All Mail"))
                conn.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
                conn.expunge()
            else:
                folder = get_folder(account, "archive")
                conn.uid("MOVE", uid, folder)
            return [TextContent(type="text", text=f"Archived email {uid} ({account_label})")]

        elif name == "babushka_junk_email":
            uid = arguments["uid"]
            folder = get_folder(account, "junk")
            conn.select(_imap_folder(arguments.get("from_folder", "INBOX")))
            if account.get("provider") == "gmail":
                conn.uid("COPY", uid, _imap_folder(folder))
                conn.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
                conn.expunge()
            else:
                conn.uid("MOVE", uid, folder)
            return [TextContent(type="text", text=f"Moved email {uid} to Junk ({account_label})")]

        elif name == "babushka_trash_email":
            uid = arguments["uid"]
            folder = get_folder(account, "trash")
            conn.select(_imap_folder(arguments.get("from_folder", "INBOX")))
            if account.get("provider") == "gmail":
                conn.uid("COPY", uid, _imap_folder(folder))
                conn.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
                conn.expunge()
            else:
                conn.uid("MOVE", uid, folder)
            return [TextContent(type="text", text=f"Moved email {uid} to Trash ({account_label})")]

        elif name == "babushka_move_email":
            uid = arguments["uid"]
            to_folder = arguments["to_folder"]
            conn.select(_imap_folder(arguments.get("from_folder", "INBOX")))
            if account.get("provider") == "gmail":
                conn.uid("COPY", uid, _imap_folder(to_folder))
                conn.uid("STORE", uid, "+FLAGS", "(\\Deleted)")
                conn.expunge()
            else:
                conn.uid("MOVE", uid, to_folder)
            return [TextContent(type="text", text=f"Moved email {uid} to {to_folder} ({account_label})")]

        elif name == "babushka_create_folder":
            folder_name = arguments["folder_name"]
            status, response = conn.create(folder_name)
            if status == "OK":
                return [TextContent(type="text", text=f"Created folder: {folder_name} ({account_label})")]
            else:
                return [TextContent(type="text", text=f"Failed to create folder: {response} ({account_label})")]

        elif name == "babushka_list_folders":
            _, folders = conn.list()
            folder_names = []
            for f in folders:
                decoded = f.decode()
                # Parse IMAP LIST response: (flags) "delimiter" name
                match = re.match(r'\(.*?\)\s+"(.+?)"\s+(.+)', decoded)
                if match:
                    folder_names.append(match.group(2).strip('"'))
            result = {"account": account_label, "folders": folder_names}
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except Exception as e:
        return [TextContent(type="text", text=f"Error ({account_label}): {e}")]
    finally:
        try:
            conn.logout()
        except Exception:
            pass


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
