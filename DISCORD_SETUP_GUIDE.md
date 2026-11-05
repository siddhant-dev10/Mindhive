# AgentHive — Discord Developer Portal Setup Guide (`DISCORD_SETUP_GUIDE.md`)

This guide walks you through registering and connecting your Discord bot to **AgentHive**.

---

## 1. Create Application in Discord Developer Portal

1. Navigate to the **[Discord Developer Portal](https://discord.com/developers/applications)**.
2. Click **New Application** in the top right corner.
3. Set the name to **`AgentHive`** and accept the Terms of Service.
4. Copy your **Application ID** and paste it into `.env`:
   ```bash
   DISCORD_APPLICATION_ID=<your_application_id>
   ```

---

## 2. Configure Bot Identity & Secrets

1. In the left sidebar, click **Bot**.
2. Click **Add Bot** (or confirm).
3. Under **Username**, set `AgentHive Bot`.
4. Click **Reset Token** to generate a fresh bot token.
5. **Copy the token immediately** and add it to `.env`:
   ```bash
   DISCORD_BOT_TOKEN=<your_bot_token>
   ```
   > [!CAUTION]
   > Never commit `.env` or share your bot token publicly. AgentHive will never ask for your personal Discord account password.

---

## 3. Enable Privileged Gateway Intents

Under the **Bot** page, scroll down to **Privileged Gateway Intents**:
- ✅ **MESSAGE CONTENT INTENT** (Required: enables reading slash commands & instructions)
- ✅ **SERVER MEMBERS INTENT** (Recommended: allows identifying Project Owner roles)

Click **Save Changes**.

---

## 4. Set Bot Permissions & Generate Invite URL

1. In the left sidebar, go to **OAuth2** -> **URL Generator**.
2. Under **Scopes**, select:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Under **Bot Permissions**, select:
   - ✅ `View Channels`
   - ✅ `Send Messages`
   - ✅ `Send Messages in Threads`
   - ✅ `Create Public Threads`
   - ✅ `Manage Webhooks`
   - ✅ `Embed Links`
   - ✅ `Attach Files`
   - ✅ `Read Message History`
4. Copy the generated URL at the bottom of the page.
5. Paste the URL into your browser, select your Discord server (Guild), and click **Authorize**.

---

## 5. Identify Guild & Channel IDs

1. In your Discord client, open **Settings** -> **Advanced** -> toggle **Developer Mode** to ON.
2. Right-click your Discord server icon -> click **Copy Server ID**.
   Add it to `.env`:
   ```bash
   DISCORD_GUILD_ID=<your_guild_id>
   ```
3. Right-click your desired text channel (e.g. `#agenthive-lounge`) -> click **Copy Channel ID**.
   Add it to `.env`:
   ```bash
   DISCORD_LOUNGE_CHANNEL_ID=<your_channel_id>
   ```

---

## 6. Supported Slash Commands

Once connected, AgentHive provides the following 9 commands:

| Command | Arguments | Purpose |
|---|---|---|
| `/newproject` | `name: string`, `description: string` | Initializes a new project and generates `PROJECT.md` |
| `/project` | `project_id: string` | Displays project details, files, and spec link |
| `/analyse` | `project_id: string` | Triggers zero-bias independent parallel agent analysis |
| `/discuss` | `project_id: string` | Launches Switch Room multi-agent debate |
| `/assign` | `project_id: string` | Hermes synthesizes consensus and proposes WBS tasks |
| `/approve` | `project_id: string`, `[task_code: string]` | Sovereign Human Approval Gate |
| `/reject` | `project_id: string`, `[reason: string]` | Pauses or aborts project proposal |
| `/status` | `project_id: string` | Live status dashboard of project and agents |
| `/report` | `project_id: string` | Executes tasks, runs adversarial tests, compiles report |

---

## 7. Interactive Approval Buttons & Headless Dual-Mode

### Interactive Button Approval (`ApprovalView`)
When Hermes delivers the WBS proposal via `/assign`, the Discord bot attaches an interactive action row:
- **✅ Approve & Run (Green Button):** Automatically grants sovereign human approval and executes tasks immediately.
- **❌ Reject (Red Button):** Freezes execution and marks the project state as `ABORTED`.

### Zero-Friction Dual-Mode Dispatcher
If `DISCORD_BOT_TOKEN` is not yet populated:
- AgentHive runs in **Headless Command Dispatcher Mode**.
- All 9 slash command handlers (`cmd_newproject`, `cmd_analyse`, `cmd_discuss`, `cmd_assign`, `cmd_approve`, `cmd_status`, `cmd_report`) are 100% executable programmatically via Python CLI, pytest suites, or REST API endpoints (`/api/projects/...`).
- When credentials are provided in `.env`, the live bot connects automatically at startup without any code modifications.
