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
        if r.status != 200:
            return None
        accounts = await r.json()
    match = next((a for a in accounts if a.get("name") == name or a.get("username") == name), None)
    return match["id"] if match else None


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


@client.event
async def on_ready():
    await tree.sync()
    print(f"[control-bot] Logged in as {client.user} — slash commands synced.")


if __name__ == "__main__":
    client.run(BOT_TOKEN)
