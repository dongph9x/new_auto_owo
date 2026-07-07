# This file is part of NeuraSelf-UwU.
# Copyright (c) 2025-Present Routo
#
# NeuraSelf-UwU is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# You should have received a copy of the GNU General Public License
# along with NeuraSelf-UwU. If not, see <https://www.gnu.org/licenses/>.

import re
import time
import discord
from discord.ext import commands
from utils import history_tracker as ht

UUID_RE = re.compile(r'battle-log\?uuid=([0-9a-fA-F-]{36})')
_STREAK_PATTERNS = (
    re.compile(r'lost (?:your )?(?:\*\*)?(\d+)(?:\*\*)? win streak', re.IGNORECASE),
    re.compile(r'(\d+)\s*win streak', re.IGNORECASE),
    re.compile(r'win streak[:\s]*(\d+)', re.IGNORECASE),
    re.compile(r'streak[:\s]*(\d+)', re.IGNORECASE),
)


def parse_loss_streak(text, raw_json=None):
    """Win streak at the moment of loss (from OwO message text, then API JSON)."""
    for pat in _STREAK_PATTERNS:
        m = pat.search(text or "")
        if m:
            return int(m.group(1))
    if raw_json:
        return _streak_from_json(raw_json)
    return None


def _streak_from_json(data):
    if not isinstance(data, dict):
        return None
    for key in ('streak', 'winStreak', 'win_streak'):
        val = data.get(key)
        if isinstance(val, (int, float)):
            return int(val)
    for section in data.values():
        if isinstance(section, dict):
            found = _streak_from_json(section)
            if found is not None:
                return found
    return None


class BattleLogger(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # De-dupe: OwO edits the battle message (on_message + on_message_edit both
        # fire), and we don't want to store/fetch the same battle twice.
        self._seen_uuids = {}

    @commands.Cog.listener()
    async def on_message(self, message):
        await self._process(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        await self._process(after)

    async def _process(self, message):
        if str(message.author.id) != str(self.bot.owo_bot_id):
            return
        all_channels = [str(c) for c in self.bot.channels]
        if str(message.channel.id) not in all_channels:
            return
        if not self.bot.is_message_for_me(message):
            return

        text = self._full_text(message)
        if 'you lost' not in text.lower():
            return

        uuid_match = UUID_RE.search(text)
        uuid = uuid_match.group(1) if uuid_match else None

        now = time.time()
        self._seen_uuids = {u: t for u, t in self._seen_uuids.items() if now - t < 120}
        dedupe_key = uuid or f"nouuid:lose:{int(now // 5)}"
        if dedupe_key in self._seen_uuids:
            return
        self._seen_uuids[dedupe_key] = now

        battle_link = f"https://owobot.com/battle-log?uuid={uuid}" if uuid else None

        raw_json = None
        if uuid:
            raw_json = await self.bot.web_solver.fetch_battle_log(uuid)

        streak = parse_loss_streak(text, raw_json)
        if raw_json is not None:
            self.bot.log("INFO", f"BattleLog: fetched loss detail (streak {streak}).")

        try:
            ht.record_battle(
                account_id=str(self.bot.user.id),
                result='lose',
                streak=streak,
                uuid=uuid,
                battle_link=battle_link,
                raw_json=raw_json,
            )
        except Exception as e:
            self.bot.log("ERROR", f"BattleLog: failed to record battle: {e}")

    def _full_text(self, message):
        parts = [message.content or ""]
        for em in message.embeds:
            if em.title: parts.append(em.title)
            if em.description: parts.append(em.description)
            if em.url: parts.append(em.url)
            if em.author and em.author.name: parts.append(em.author.name)
            if em.author and em.author.url: parts.append(em.author.url)
            if em.footer and em.footer.text: parts.append(em.footer.text)
            for f in em.fields:
                parts.append(f"{f.name} {f.value}")
        # Buttons/link components sometimes carry the battle-log URL.
        for comp in getattr(message, 'components', []) or []:
            for child in getattr(comp, 'children', []) or []:
                url = getattr(child, 'url', None)
                if url:
                    parts.append(str(url))
        return "\n".join(p for p in parts if p)


async def setup(bot):
    await bot.add_cog(BattleLogger(bot))
