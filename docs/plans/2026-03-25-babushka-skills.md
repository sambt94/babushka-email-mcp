# Babushka Skills System — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a setup wizard, send/reply, daily briefing, unsubscribe sweep, folder organiser, and auto-rules learning to Babushka God Mode.

**Architecture:** New MCP tools in `server.py` (send_email via SMTP, read HTML body, create folder) + expanded skill instructions in `CLAUDE.md` that Claude follows as workflows. Most intelligence is prompt-driven, tools just provide capabilities.

**Tech Stack:** Python imaplib (existing), smtplib (new, stdlib), mcp SDK

---

### Task 1: Send Email Tool (SMTP)

**Files:**
- Modify: `server.py` — add `get_smtp_connection()` helper and `babushka_send_email` tool

**Step 1: Add SMTP helper function**

Add after `get_imap_connection()` (~line 41):

```python
import smtplib
from email.mime.text import MIMEText

def get_smtp_connection(config):
    provider = config.get("provider", "icloud")
    servers = {
        "icloud": "smtp.mail.me.com",
        "gmail": "smtp.gmail.com",
        "outlook": "smtp.office365.com",
    }
    host = servers.get(provider, config.get("smtp_host", ""))
    smtp = smtplib.SMTP(host, 587)
    smtp.starttls()
    smtp.login(config["email"], config["password"])
    return smtp
```

**Step 2: Add tool definition**

Add to `list_tools()` return list:

```python
Tool(
    name="babushka_send_email",
    description="Send an email. Use for replies, forwarding summaries, or any outbound email.",
    inputSchema={
        "type": "object",
        "properties": {
            "to": {"type": "string", "description": "Recipient email address"},
            "subject": {"type": "string", "description": "Email subject line"},
            "body": {"type": "string", "description": "Plain text email body"},
        },
        "required": ["to", "subject", "body"],
    },
),
```

**Step 3: Add tool handler**

Add before the `babushka_list_folders` handler:

```python
elif name == "babushka_send_email":
    to_addr = arguments["to"]
    subject = arguments["subject"]
    body = arguments["body"]
    msg = MIMEText(body)
    msg["From"] = config["email"]
    msg["To"] = to_addr
    msg["Subject"] = subject
    smtp = get_smtp_connection(config)
    smtp.send_message(msg)
    smtp.quit()
    return [TextContent(type="text", text=f"Sent email to {to_addr}: {subject}")]
```

**Step 4: Test manually**

Restart MCP server, then in Claude Code:
> "Send a test email to yourself with subject 'Babushka test'"

Expected: Email arrives in inbox.

**Step 5: Commit**

```bash
git add server.py
git commit -m "feat: add babushka_send_email tool (SMTP)"
```

---

### Task 2: Read Email HTML Tool

**Files:**
- Modify: `server.py` — add `get_html_body()` helper and `babushka_read_email_html` tool

**Step 1: Add HTML body extractor**

Add after `get_body()` function:

```python
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
```

**Step 2: Add tool definition**

```python
Tool(
    name="babushka_read_email_html",
    description="Read email HTML body. Use to find unsubscribe links, tracking pixels, or formatted content.",
    inputSchema={
        "type": "object",
        "properties": {
            "uid": {"type": "string", "description": "Email UID"},
            "folder": {"type": "string", "description": "Folder the email is in", "default": "INBOX"},
        },
        "required": ["uid"],
    },
),
```

**Step 3: Add tool handler**

Add after the `babushka_read_email` handler:

```python
elif name == "babushka_read_email_html":
    uid = arguments["uid"]
    folder = arguments.get("folder", "INBOX")
    conn.select(folder, readonly=True)
    _, msg_data = conn.uid("fetch", uid, "(RFC822)")
    if msg_data[0] is None:
        return [TextContent(type="text", text="Email not found")]
    raw = msg_data[0][1]
    msg = email.message_from_bytes(raw)
    html = get_html_body(msg)
    if not html:
        return [TextContent(type="text", text="No HTML body found in this email")]
    # Extract unsubscribe links
    import re
    unsub_links = re.findall(r'href="([^"]*(?:unsubscribe|opt.out|remove)[^"]*)"', html, re.IGNORECASE)
    result = {
        "uid": uid,
        "html_preview": html[:4000],
        "unsubscribe_links": unsub_links,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]
```

**Step 4: Test manually**

> "Read the HTML of my latest marketing email and find unsubscribe links"

**Step 5: Commit**

```bash
git add server.py
git commit -m "feat: add babushka_read_email_html with unsubscribe link extraction"
```

---

### Task 3: Create Folder Tool

**Files:**
- Modify: `server.py` — add `babushka_create_folder` tool

**Step 1: Add tool definition**

```python
Tool(
    name="babushka_create_folder",
    description="Create a new email folder/mailbox.",
    inputSchema={
        "type": "object",
        "properties": {
            "folder_name": {"type": "string", "description": "Name for the new folder"},
        },
        "required": ["folder_name"],
    },
),
```

**Step 2: Add tool handler**

Add before the `babushka_list_folders` handler:

```python
elif name == "babushka_create_folder":
    folder_name = arguments["folder_name"]
    status, response = conn.create(folder_name)
    if status == "OK":
        return [TextContent(type="text", text=f"Created folder: {folder_name}")]
    else:
        return [TextContent(type="text", text=f"Failed to create folder: {response}")]
```

**Step 3: Test manually**

> "Create a folder called 'Receipts'"

Then: "List my folders" to verify it appears.

**Step 4: Commit**

```bash
git add server.py
git commit -m "feat: add babushka_create_folder tool"
```

---

### Task 4: Setup Wizard Skill

**Files:**
- Modify: `CLAUDE.md` — add setup wizard instructions

**Step 1: Add wizard section to CLAUDE.md**

Add after the "What Users Can Say" section:

```markdown
## Skills

### Setup Wizard
**Trigger:** "set up my rules" / "customise babushka" / "create my rules" / first-time use

Ask these questions ONE AT A TIME:

1. "How aggressive should spam filtering be?"
   - Relaxed: only flag obvious phishing
   - Moderate: flag suspicious senders too
   - Aggressive: zero tolerance, flag anything unknown

2. "Which domains should I always trust? (e.g. your employer, bank, school)"
   - Accept a comma-separated list
   - Always include apple.com, google.com by default

3. "What should I do with marketing emails?"
   - Keep in inbox
   - Archive automatically
   - Move to a 'Marketing' folder

4. "What about newsletters?"
   - Keep in inbox
   - Suggest batch-reading
   - Archive after 7 days

5. "Any senders you want to always block?"
   - Accept a list or "none"

After all questions, generate a complete `babushka-rules.md` and save it.
Show the user the generated rules and ask "Does this look right, dear?"
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "feat: add setup wizard skill to CLAUDE.md"
```

---

### Task 5: Daily Briefing Skill

**Files:**
- Modify: `CLAUDE.md` — add daily briefing instructions

**Step 1: Add briefing section**

```markdown
### Daily Briefing
**Trigger:** "what's important today?" / "daily briefing" / "morning summary"

1. List last 24 hours of emails from all connected providers
2. Read the subject + sender of each
3. Categorise using babushka-rules.md
4. Present a summary:

"Good morning, dear! Here's what came in overnight:

📬 X new emails
✅ X important — [quick summary of each]
📰 X newsletters — [list titles]
📦 X marketing — shall I archive these?
🔴 X suspicious — [details]

Your most important email is from [sender] about [topic]."

5. Offer actions: "Want me to clean up the marketing and junk?"
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "feat: add daily briefing skill"
```

---

### Task 6: Quick Reply Skill

**Files:**
- Modify: `CLAUDE.md` — add reply instructions

**Step 1: Add reply section**

```markdown
### Quick Reply
**Trigger:** "reply to [email]" / "tell them [message]" / "respond to [sender]"

1. Read the full email using babushka_read_email
2. Draft a reply in the user's voice (concise, friendly, professional)
3. Show the draft: "Here's what I'd send back, dear:"
4. Wait for approval or edits
5. Send using babushka_send_email with:
   - to: original sender's email
   - subject: "Re: [original subject]"
   - body: the approved draft

NEVER send without explicit approval.
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "feat: add quick reply skill"
```

---

### Task 7: Unsubscribe Sweep Skill

**Files:**
- Modify: `CLAUDE.md` — add unsubscribe instructions

**Step 1: Add unsubscribe section**

```markdown
### Unsubscribe Sweep
**Trigger:** "unsubscribe sweep" / "find things to unsubscribe from" / "too many newsletters"

1. List last 50 emails
2. Identify marketing + newsletter senders
3. Group by sender domain, count frequency
4. For senders appearing 3+ times, use babushka_read_email_html to find unsubscribe links
5. Present a list:

"Here are your most frequent marketing senders, dear:

| Sender | Emails this month | Unsubscribe link |
|--------|------------------|-----------------|
| Codecademy | 8 | [link] |
| Fastic | 5 | [link] |

Want me to open any of these unsubscribe links for you?
I can also junk all emails from any of these senders."

6. On confirmation, junk selected senders' emails
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "feat: add unsubscribe sweep skill"
```

---

### Task 8: Folder Organiser Skill

**Files:**
- Modify: `CLAUDE.md` — add folder organiser instructions

**Step 1: Add organiser section**

```markdown
### Folder Organiser
**Trigger:** "organise my folders" / "sort emails into folders" / "create a folder for [topic]"

1. List current folders using babushka_list_folders
2. Scan recent emails and identify natural groupings
3. Suggest folder structure:

"Looking at your emails, dear, I'd suggest:

- **Receipts** — for order confirmations and invoices
- **Job Search** — for LinkedIn, recruiter, and interview emails
- **Newsletters** — for your regular subscriptions

Shall I create these and sort your recent emails into them?"

4. On approval:
   - Create folders using babushka_create_folder
   - Move relevant emails using babushka_move_email
   - Report what was moved where
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "feat: add folder organiser skill"
```

---

### Task 9: Auto-Rules Learning Skill

**Files:**
- Modify: `CLAUDE.md` — add learning instructions

**Step 1: Add learning section**

```markdown
### Learn My Patterns
**Trigger:** "learn from what I did" / "update my rules" / after any cleanup session

After the user takes actions (archive, junk, move), analyse the patterns:

1. Look at what was archived/junked/kept in this session
2. Identify patterns:
   - "You archived 5 emails from codecademy.com — add to auto-archive?"
   - "You kept all emails from craft.do — add to trusted senders?"
   - "You junked 3 emails with .xyz domains — add .xyz to suspicious TLDs?"
3. Present suggestions:

"Based on what you did today, dear, I'd suggest updating your rules:

1. ✅ Add craft.do to trusted senders
2. 📦 Auto-archive emails from codecademy.com
3. 🔴 Add .xyz to suspicious TLDs

Shall I update babushka-rules.md with these?"

4. On approval, edit babushka-rules.md with the new rules
```

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "feat: add auto-rules learning skill"
```

---

### Task 10: Update CLAUDE.md Available Actions + What Users Can Say

**Files:**
- Modify: `CLAUDE.md` — update tool list and trigger phrases

**Step 1: Update Available Actions to include new tools**

Replace the current "Available Actions" section with the full list including `babushka_send_email`, `babushka_read_email_html`, `babushka_create_folder`.

**Step 2: Update "What Users Can Say" with new triggers**

Add all the new skill trigger phrases.

**Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with all new tools and skill triggers"
```

---

### Task 11: Update README

**Files:**
- Modify: `README.md` — add skills section

**Step 1: Add skills overview to README**

Add a "Skills" section listing all 6 skills with one-line descriptions and example trigger phrases.

**Step 2: Update tools table with new tools**

**Step 3: Commit and push**

```bash
git add README.md CLAUDE.md server.py
git commit -m "feat: complete Babushka skills system"
git push
```
