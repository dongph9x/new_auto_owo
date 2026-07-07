# Slash-command control bot for NeuraSelf.
#
# This is a SEPARATE, real Discord Application (bot token + applications.commands
# scope) — not one of the self-bot farming accounts. It never touches Discord
# directly on their behalf; it only calls the dashboard's HTTP API
# (/api/accounts/list, /api/control) over the network, authenticated with
# CONTROL_API_TOKEN. It runs in its own container because it depends on the real
# `discord.py` package, which can't be installed alongside `discord.py-self` (both
# provide the `discord` module).

import os
import json
import discord
from discord import app_commands
import aiohttp

BOT_TOKEN = os.environ["CONTROL_BOT_TOKEN"]
DASHBOARD_URL = os.environ.get("DASHBOARD_URL", "http://neuraself:8000").rstrip("/")
ACCOUNTS_FILE = os.environ.get("ACCOUNTS_FILE", "/app/config/accounts.json")
AUTH_FILE = os.environ.get("AUTH_FILE", "/app/config/auth.json")


def load_control_api_token():
    # Prefer an explicit env override; otherwise read the token the dashboard
    # auto-generated into auth.json (config/ is mounted read-only into this
    # container too), so there's nothing to manually copy/sync.
    env_token = os.environ.get("CONTROL_API_TOKEN")
    if env_token:
        return env_token
    try:
        with open(AUTH_FILE, "r") as f:
            return json.load(f).get("control_api_token")
    except Exception:
        return None


CONTROL_API_TOKEN = load_control_api_token()
if not CONTROL_API_TOKEN:
    raise RuntimeError(
        "No control_api_token found — start the main neuraself service at least once "
        "so it can generate config/auth.json, then restart this container."
    )

intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def load_accounts():
    try:
        with open(ACCOUNTS_FILE, "r") as f:
            return json.load(f).get("accounts", [])
    except Exception:
        return []


def accounts_manageable_by(user_id: int):
    """Each NeuraSelf account belongs to exactly one Discord user — the one whose
    ID matches its "dc_user_id" in accounts.json."""
    return [a for a in load_accounts() if str(a.get("dc_user_id", "")) == str(user_id)]


def is_allowed_for_account(interaction: discord.Interaction, account_name: str) -> bool:
    account = next((a for a in load_accounts() if a.get("name") == account_name), None)
    return bool(account) and str(account.get("dc_user_id", "")) == str(interaction.user.id)


async def account_autocomplete(interaction: discord.Interaction, current: str):
    # Only offer accounts this user is actually allowed to touch, so the picker
    # doubles as a quiet permission boundary too.
    names = [a["name"] for a in accounts_manageable_by(interaction.user.id) if a.get("name")]
    return [app_commands.Choice(name=n, value=n) for n in names if current.lower() in n.lower()][:25]


async def resolve_account_id(session: aiohttp.ClientSession, name: str):
    headers = {"Authorization": f"Bearer {CONTROL_API_TOKEN}"}
    async with session.get(f"{DASHBOARD_URL}/api/accounts/list", headers=headers) as r:
        if r.status == 200:
            accounts = await r.json()
            match = next((a for a in accounts if a.get("name") == name or a.get("username") == name), None)
            if match:
                return match["id"]
    # Offline fallback — battle history lives in SQLite, not in a live bot instance.
    for a in load_accounts():
        if a.get("name") == name:
            aid = a.get("id") or a.get("user_id")
            return str(aid) if aid else None
    return None


async def send_control_action(action: str, name: str):
    headers = {"Authorization": f"Bearer {CONTROL_API_TOKEN}"}
    async with aiohttp.ClientSession() as session:
        account_id = await resolve_account_id(session, name)
        if not account_id:
            return False, "Account not found or not currently online"
        async with session.post(
            f"{DASHBOARD_URL}/api/control",
            headers=headers,
            json={"action": action, "id": account_id},
        ) as r:
            if r.status != 200:
                return False, f"Dashboard returned HTTP {r.status}"
            data = await r.json()
            return bool(data.get("success")), None


def api_headers():
    return {"Authorization": f"Bearer {CONTROL_API_TOKEN}"}


async def resolve_account_id_for_user(session: aiohttp.ClientSession, interaction: discord.Interaction, account: str):
    if not is_allowed_for_account(interaction, account):
        return None, f"You're not authorized to manage **{account}**."
    account_id = await resolve_account_id(session, account)
    if not account_id:
        return None, f"Account **{account}** not found (bot may be offline)."
    return account_id, None


async def dashboard_get(path: str, params: dict | None = None):
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{DASHBOARD_URL}{path}", headers=api_headers(), params=params or {}) as r:
            try:
                data = await r.json()
            except Exception:
                data = {}
            return r.status, data


def split_discord_message(text: str, limit: int = 1900):
    """Split long text into chunks that fit Discord's message limit."""
    if len(text) <= limit:
        return [text]
    chunks = []
    while text:
        if len(text) <= limit:
            chunks.append(text)
            break
        split_at = text.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(text[:split_at])
        text = text[split_at:].lstrip("\n")
    return chunks


def format_losses_embed(account: str, battles: list) -> discord.Embed:
    embed = discord.Embed(
        title=f"❌ Losses — {account}",
        color=0xEF4444,
    )

    if not battles:
        embed.description = "_Chưa có trận thua nào được ghi._"
        return embed

    lines = []
    for b in battles:
        bid = b.get("id", "?")
        ts = b.get("timestamp", "?")
        streak = b.get("streak")
        streak_part = f" · streak **{streak}**" if streak is not None else ""
        link = b.get("battle_link")
        link_part = f" · [log]({link})" if link else ""
        lines.append(f"**#{bid}** · `{ts}`{streak_part}{link_part}")

    body = "\n".join(lines)
    if len(body) > 4000:
        body = body[:3997] + "…"
    embed.description = body
    return embed


@tree.command(name="pause", description="Pause a NeuraSelf account")
@app_commands.describe(account="The account to pause")
@app_commands.autocomplete(account=account_autocomplete)
async def pause_cmd(interaction: discord.Interaction, account: str):
    if not is_allowed_for_account(interaction, account):
        await interaction.response.send_message(f"You're not authorized to manage **{account}**.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    ok, err = await send_control_action("stop", account)
    if ok:
        await interaction.followup.send(f"⏸️ Paused **{account}**.", ephemeral=True)
    else:
        await interaction.followup.send(f"❌ Failed to pause **{account}**: {err or 'unknown error'}", ephemeral=True)


@tree.command(name="start", description="Resume a NeuraSelf account")
@app_commands.describe(account="The account to resume")
@app_commands.autocomplete(account=account_autocomplete)
async def start_cmd(interaction: discord.Interaction, account: str):
    if not is_allowed_for_account(interaction, account):
        await interaction.response.send_message(f"You're not authorized to manage **{account}**.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    ok, err = await send_control_action("start", account)
    if ok:
        await interaction.followup.send(f"▶️ Resumed **{account}**.", ephemeral=True)
    else:
        await interaction.followup.send(f"❌ Failed to resume **{account}**: {err or 'unknown error'}", ephemeral=True)


@tree.command(name="battles", description="Trận thua gần nhất (id · thời gian · link log)")
@app_commands.describe(
    account="Account cần xem",
    limit="Số trận thua cần lấy (1–20)",
)
@app_commands.autocomplete(account=account_autocomplete)
async def battles_cmd(
    interaction: discord.Interaction,
    account: str,
    limit: app_commands.Range[int, 1, 20] = 10,
):
    await interaction.response.defer(ephemeral=True)
    async with aiohttp.ClientSession() as session:
        account_id, err = await resolve_account_id_for_user(session, interaction, account)
    if err:
        await interaction.followup.send(err, ephemeral=True)
        return

    status, data = await dashboard_get("/api/battles", {
        "id": account_id,
        "limit": limit,
        "result": "lose",
    })
    if status != 200:
        await interaction.followup.send(f"❌ Dashboard HTTP {status}", ephemeral=True)
        return
    if data.get("error"):
        await interaction.followup.send(f"❌ {data['error']}", ephemeral=True)
        return

    embed = format_losses_embed(account, data.get("battles") or [])
    await interaction.followup.send(embed=embed, ephemeral=True)


@tree.command(name="analyze", description="AI analysis of battle log(s) by ID or recent losses (ChatGPT)")
@app_commands.describe(
    account="The account to analyse",
    battle_id="Log ID from /battles (e.g. 42 or 42,43). Leave empty for recent losses.",
)
@app_commands.autocomplete(account=account_autocomplete)
async def analyze_cmd(interaction: discord.Interaction, account: str, battle_id: str = None):
    await interaction.response.defer(ephemeral=True)
    async with aiohttp.ClientSession() as session:
        account_id, err = await resolve_account_id_for_user(session, interaction, account)
    if err:
        await interaction.followup.send(err, ephemeral=True)
        return

    params = {"id": account_id}
    if battle_id and battle_id.strip():
        params["battle_id"] = battle_id.strip()

    status, data = await dashboard_get("/api/battles/analyze", params)
    if status != 200:
        await interaction.followup.send(f"❌ Dashboard HTTP {status}", ephemeral=True)
        return

    if not data.get("success"):
        await interaction.followup.send(f"❌ {data.get('error', 'Analysis failed')}", ephemeral=True)
        return

    summary = data.get("summary", "")
    counts = data.get("counts") or {}
    wr = counts.get("win_rate")
    wr_part = f" ({wr}% WR)" if wr is not None else ""
    ids = data.get("battle_ids") or []
    id_part = f" · log **#{', #'.join(str(i) for i in ids)}**" if ids else ""
    header = (
        f"🧠 **Battle analysis — {account}**{id_part}\n"
        f"Record: {counts.get('wins', 0)}W / {counts.get('loses', 0)}L{wr_part}\n\n"
    )
    for chunk in split_discord_message(header + summary):
        await interaction.followup.send(chunk, ephemeral=True)


@client.event
async def on_ready():
    await tree.sync()
    print(f"[control-bot] Logged in as {client.user} — slash commands synced.")


if __name__ == "__main__":
    client.run(BOT_TOKEN)
