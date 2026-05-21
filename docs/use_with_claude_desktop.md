# Use with Claude Desktop

This is an optional add-on to the EHF Fellows Directory app. Once set up,
you can ask **Claude Desktop** questions about the directory and your
saved groups, and have it draft outreach emails for you to review and
send.

Example things you can ask:

- *"How many fellows are based in Aotearoa?"*
- *"Find the fellow who runs that climate finance fund — I forget the name."*
- *"List my saved groups."*
- *"Who's in my Climate Action group?"*
- *"Draft an email to my Climate Action group inviting them to meet
  Thursday at 1pm NZ time — don't send, just stage it for me to review."*

Claude reads your **local** copy of the directory to answer. For the
email demo, it hands the draft back to you as a pre-filled compose
window in your mail app — you always click Send.

This is optional. The Fellows app works perfectly well without it.

---

## Before you start

You should already have:

- The **Fellows Directory app** installed and working (you've used it, you have
  groups).
- **Claude Desktop** installed.
- A Mac.
- About 15 minutes.

You'll also need **GitHub access** to download the project files — if you
don't have it, ask Rich first.

---

## What you're going to do (overview)

1. Download a small folder of connector files.
2. Drop two copies of your data into that folder (the fellows directory
   + your groups).
3. Run one Terminal command to install the connector's helpers.
4. Tell Claude Desktop where the folder lives.
5. Quit and reopen Claude Desktop. Done.

The connectors only run when Claude calls them. Nothing extra runs in
the background.

---

## Step 1 — Download the connector files

1. Open <https://github.com/richbodo/fellows_local_db> in your browser.
   (If you see "404 Not Found," ask Rich for repo access.)
2. Click the green **Code** button → **Download ZIP**.
3. Open the downloaded zip — it creates a folder called
   `fellows_local_db-main` in your **Downloads** folder.
4. In Finder, **drag that folder into your home folder** (the one with the
   little house icon in the sidebar, named after you).
5. **Rename** it from `fellows_local_db-main` to just `fellows_local_db`.

When you're done, in Finder you should see a folder called
`fellows_local_db` directly inside your home folder.

> **What's my Mac username?** Open Finder → menu bar → **Go → Home**. The
> window title is your username. You'll need it again in Step 4.

---

## Step 2 — Copy your data into the folder

You need two data files: **the fellows directory** (everyone's profile)
and **your private groups**.

### 2A. The fellows directory

1. Open your usual browser (whichever you signed into the Fellows app with).
2. Go to <https://fellows.globaldonut.com/fellows.db>
3. The browser downloads a file called `fellows.db`.
   - If Safari asks whether to keep an unrecognized file type, click **Keep**.
4. In Finder, move that `fellows.db` into the `app` subfolder of your
   project folder. The final location should be:

   `~/fellows_local_db/app/fellows.db`

   (i.e. Home → `fellows_local_db` → `app` → `fellows.db`)

If a `fellows.db` is already there, replace it.

### 2B. Your private groups

1. Open the Fellows Directory app.
2. Tap/click **Settings**.
3. Click **Download a backup**.
4. A file called `relationships.db` downloads.
5. In Finder, move it into the **same** `app` subfolder:

   `~/fellows_local_db/app/relationships.db`

If a `relationships.db` is already there, replace it.

> Whenever you make new groups in the app and want Claude to see them,
> just redo this step.

---

## Step 3 — Install the connector's helpers

This is the only step that uses Terminal. We do it once.

1. Open the **Terminal** app: press **⌘+Space**, type "Terminal", press Return.
   A window opens with a `$` prompt.
2. Copy this whole line, paste it into Terminal, press Return:

   ```
   cd ~/fellows_local_db && python3 -m venv mcp_servers/.venv && mcp_servers/.venv/bin/pip install -r mcp_servers/requirements.txt
   ```

3. You'll see lines about downloading and installing. When the `$` prompt
   comes back (usually under a minute), it's done.

You can close Terminal now.

> **If Terminal says `python3: command not found`:** macOS will pop up an
> "Install Command Line Developer Tools" dialog. Click **Install**, wait
> for it to finish (a few minutes), then rerun the command above. This
> is a one-time Apple install — it's the developer toolkit Apple ships
> for any program that needs Python.

---

## Step 4 — Tell Claude Desktop where the connectors live

1. Open **Claude Desktop**.
2. Menu bar: **Claude → Settings…** → **Developer** tab → click
   **Edit Config**.
3. A text file opens in your default editor (TextEdit, usually).

What you do next depends on what's already in the file.

### If the file is empty or just shows `{}`

Replace whatever's there with this — but **change `richbodo` to your own
Mac username everywhere** (8 places):

```json
{
  "mcpServers": {
    "shared-data-ops": {
      "command": "/Users/richbodo/fellows_local_db/mcp_servers/.venv/bin/python",
      "args": [
        "/Users/richbodo/fellows_local_db/mcp_servers/shared_data_ops.py",
        "--db",
        "/Users/richbodo/fellows_local_db/app/fellows.db"
      ]
    },
    "private-data-ops": {
      "command": "/Users/richbodo/fellows_local_db/mcp_servers/.venv/bin/python",
      "args": [
        "/Users/richbodo/fellows_local_db/mcp_servers/private_data_ops.py",
        "--db",
        "/Users/richbodo/fellows_local_db/app/relationships.db",
        "--fellows-db",
        "/Users/richbodo/fellows_local_db/app/fellows.db"
      ]
    },
    "comms": {
      "command": "/Users/richbodo/fellows_local_db/mcp_servers/.venv/bin/python",
      "args": [
        "/Users/richbodo/fellows_local_db/mcp_servers/comms.py"
      ]
    }
  }
}
```

Save the file (**⌘S**) and close the editor.

### If the file already has stuff in it

You'll see something like `{ "preferences": { … } }`. You need to **add**
`mcpServers` as a second top-level item next to `preferences`.

Step-by-step:

1. Find the **last `}`** in the file. That's the outermost closing brace.
2. Just **before** that final `}`, add a **comma** to the line above it
   (if there isn't one already).
3. Then paste this block (with `richbodo` changed to your Mac username
   everywhere):

   ```json
   "mcpServers": {
     "shared-data-ops": {
       "command": "/Users/richbodo/fellows_local_db/mcp_servers/.venv/bin/python",
       "args": [
         "/Users/richbodo/fellows_local_db/mcp_servers/shared_data_ops.py",
         "--db",
         "/Users/richbodo/fellows_local_db/app/fellows.db"
       ]
     },
     "private-data-ops": {
       "command": "/Users/richbodo/fellows_local_db/mcp_servers/.venv/bin/python",
       "args": [
         "/Users/richbodo/fellows_local_db/mcp_servers/private_data_ops.py",
         "--db",
         "/Users/richbodo/fellows_local_db/app/relationships.db",
         "--fellows-db",
         "/Users/richbodo/fellows_local_db/app/fellows.db"
       ]
     },
     "comms": {
       "command": "/Users/richbodo/fellows_local_db/mcp_servers/.venv/bin/python",
       "args": [
         "/Users/richbodo/fellows_local_db/mcp_servers/comms.py"
       ]
     }
   }
   ```

4. Save (**⌘S**) and close.

> JSON is picky about commas and brackets. If Claude Desktop later says
> the config has an error, the comma in step 2 is the most common
> culprit. When in doubt, ask in the fellows channel — a screenshot of
> the file goes a long way.

---

## Step 5 — Quit and reopen Claude Desktop

This part matters. Closing the window isn't enough — Claude Desktop
keeps running.

1. With Claude Desktop in front, press **⌘Q** to fully quit.
2. Wait a few seconds.
3. Open Claude Desktop again.

To check the connectors loaded: **Claude → Settings… → Developer**. You
should see three entries listed: `shared-data-ops`, `private-data-ops`,
`comms`. If the page says "No servers added," go back to Step 4 — the
config file didn't load. (Usually a missing comma, or `mcpServers` got
nested inside `preferences` by accident instead of sitting next to it.)

---

## Step 6 — Try it

Start a new chat in Claude Desktop. Try these in order:

1. *"How many fellows are in the directory?"* — confirms the directory
   connector works.
2. *"List my saved groups."* — confirms the groups connector works.
3. *"Who's in my [your group name] group?"* — confirms the groups
   connector can pull member details.
4. *"Draft an email to my [your group name] group inviting them to meet
   Thursday at 1pm NZ time. Don't send — stage it for me to review."* —
   the flagship demo.

**The first time** Claude wants to use a connector, it'll pop up a
permission prompt asking you to approve the tool call. Read what it's
about to do and click **Allow**. After the first time per connector,
it won't ask again.

For the email demo, Claude will hand you back a `mailto:` link. Clicking
it opens your default mail app with **To**, **Subject**, and **Body**
pre-filled. You review, edit, and click Send — Claude never sends mail
itself.

---

## If something doesn't work

| Symptom | Most likely cause / fix |
|---|---|
| **"No servers added"** in Settings → Developer. | The config file didn't parse. Open it again, check that `mcpServers` is at the top level (a sibling of `preferences`, not nested inside it), and that every `{` has a matching `}` and every list of items is separated by commas. |
| Claude says it can't find the directory or your groups. | Either you didn't fully quit Claude Desktop with ⌘Q, or one of the paths still has the placeholder `richbodo` in it instead of your Mac username. |
| Claude tries to answer from memory and gets it wrong (e.g. wrong fellow count). | Ask again, more explicitly: *"Use the fellows database to count …"* Once it picks the connector up in a chat, it'll keep using it. |
| Terminal in Step 3 said `python3: command not found`. | Click **Install** on the Command Line Developer Tools popup, wait for it to finish, rerun the command. |
| Safari opens the `fellows.db` link as a page of gibberish instead of downloading. | Right-click (or Control-click) the link → **Download Linked File**. Or hold **Option** while clicking. |
| Your groups in Claude look out of date. | Re-do Step 2B. The connectors read whatever was in your backup at the moment you exported it. |
| Worked yesterday, broken today after a Claude Desktop update. | Quit and reopen Claude Desktop again. If still broken, re-check Step 4. |

If you're stuck, post in the fellows channel or email Rich — a screenshot
of Claude Desktop's Developer settings panel and of your config file is
the fastest way to get help.

---

## A note on privacy

When Claude Desktop uses these connectors, **the parts of your fellows
data that Claude reads get sent to Claude's servers** (Anthropic's),
because that's where Claude does its thinking. This is the same as if
you'd copy-pasted that info into a Claude chat by hand — just easier to
forget you're doing it.

- The **fellows directory** (names, bios, contact info) goes over the
  network when you ask Claude about specific fellows.
- Your **private groups** (names, members, any notes you've added) go
  over the network when you ask Claude about your groups.
- The **email connector** only stages a draft locally — but the email
  body Claude writes was composed using the fellow info above, so the
  same boundary applies.

Nothing happens unless you ask. Claude only reads what it needs to
answer the prompt you typed.

If a particular question feels too sensitive to send to Claude, just
don't use Claude for that question — the Fellows app itself shows you
the same info without any of it leaving your Mac.

You can disable any of the three connectors at any time in **Claude
Desktop → Settings → Developer**.

---

## Updating later

- **Newer fellows directory** (when Rich announces a directory update):
  redo **Step 2A**.
- **Newer copy of your groups** (any time you've added or changed groups
  in the Fellows app): redo **Step 2B**.
- **Newer connector tools** (when there are improvements to announce):
  download the latest ZIP per **Step 1**, but before replacing the
  folder, copy your `app/fellows.db` and `app/relationships.db` aside
  so you can drop them back into the fresh `app/` subfolder. Then redo
  **Step 3**.

---

For developers / curious readers: the technical reference for these
connectors (what tools each one exposes, where the typed contracts
live, how to run them standalone) is in
[`../mcp_servers/README.md`](../mcp_servers/README.md).
