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

# Loss / win indicators — OwO has used a few phrasings over versions, so keep this
# generous rather than matching one exact string.
LOSS_PHRASES = ("you lost", "you lose", "you were defeated", "lost the battle", "was defeated")
WIN_PHRASES = ("you won", "you win", "won the battle")
# Anything that marks a message as *battle-related* at all (used for debug dumps).
BATTLE_HINTS = ("battle", "goes into battle", "battle-log")

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

    def _cfg(self):
        return self.bot.config.get('battle_logging', {})

    @commands.Cog.listener()
    async def on_message(self, message):
        await self._process(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        await self._process(after)

    async def _process(self, message):
        # One outer guard so a parse/fetch hiccup can never silently kill logging.
        try:
            await self._process_inner(message)
        except Exception as e:
            self.bot.log("ERROR", f"BattleLog: unhandled error while processing message: {e}")

    async def _process_inner(self, message):
        cfg = self._cfg()
        if not cfg.get('enabled', True):
            return
        if str(message.author.id) != str(self.bot.owo_bot_id):
            return
        all_channels = [str(c) for c in self.bot.channels]
        if str(message.channel.id) not in all_channels:
            return

        text = self._full_text(message)
        low = text.lower()

        uuid_match = UUID_RE.search(text)
        uuid = uuid_match.group(1) if uuid_match else None

        is_loss = any(p in low for p in LOSS_PHRASES)
        is_win = any(p in low for p in WIN_PHRASES)

        # Debug: dump anything battle-ish so we can see OwO's real format if detection
        # ever misses. Turn on with battle_logging.debug = true, off once confirmed.
        if cfg.get('debug', False) and (uuid or any(h in low for h in BATTLE_HINTS)):
            preview = text.replace("\n", " ⏎ ")[:500]
            self.bot.log("DEBUG", f"BattleLog raw: loss={is_loss} win={is_win} uuid={uuid} | {preview}")

        if not is_loss:
            return  # we only persist losses

        # A uuid link proves *someone* got a battle-log, but not necessarily us: when two
        # accounts share a channel (e.g. two of the user's bots farming each other), both
        # bots see the exact same message, so the uuid alone can't tell them apart.
        # Always require the identity check, or both accounts end up recording the same
        # battle as their own loss.
        if not self.bot.is_message_for_me(message):
            if cfg.get('debug', False):
                self.bot.log("DEBUG", "BattleLog: loss text but not-for-me — skipping.")
            return

        now = time.time()
        self._seen_uuids = {u: t for u, t in self._seen_uuids.items() if now - t < 120}
        dedupe_key = uuid or f"nouuid:lose:{int(now // 5)}"
        if dedupe_key in self._seen_uuids:
            return
        self._seen_uuids[dedupe_key] = now

        battle_link = f"https://owobot.com/battle-log?uuid={uuid}" if uuid else None

        raw_json = None
        fetch_on = cfg.get('fetch_detail_on', 'lose')
        if uuid and fetch_on in ('lose', 'all'):
            solver = getattr(self.bot, 'web_solver', None)
            if solver is not None:
                try:
                    raw_json = await solver.fetch_battle_log(uuid)
                except Exception as e:
                    self.bot.log("ERROR", f"BattleLog: fetch_battle_log raised: {e}")

        streak = parse_loss_streak(text, raw_json)

        try:
            ht.record_battle(
                account_id=str(self.bot.user.id),
                result='lose',
                streak=streak,
                uuid=uuid,
                battle_link=battle_link,
                raw_json=raw_json,
            )
            detail = "with detail" if raw_json is not None else "no detail"
            self.bot.log("INFO", f"BattleLog: recorded loss (streak {streak}, {detail}).")
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
