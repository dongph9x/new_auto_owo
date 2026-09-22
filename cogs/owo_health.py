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

import asyncio
import random
import re
import time

import aiohttp
from discord.ext import commands

# Tuning lives here on purpose — this monitor is not exposed in settings.json.
INTERVAL_MINUTES = [1, 2, 3]   # one of these is picked at random before every ping
INTERVAL_JITTER_S = 10         # so pings never land on an exact minute boundary
CONFIRM_INTERVAL_S = (5, 8)    # after a bad ping, re-check quickly (random delay) to confirm the outage
RECOVERY_INTERVAL_S = (15, 30) # while paused by this cog, re-ping after a random delay in this range
LATENCY_THRESHOLD_MS = 100      # OwO's own reported latency above this counts as "down"
RESPONSE_TIMEOUT_S = 5         # no pong within this window also counts as "down"
FAIL_STREAK = 3                # consecutive bad checks required before pausing
AUTO_RESUME = True             # un-pause by itself once OwO answers healthily again
ALERT_ON_RECOVER = True        # also webhook the recovery, not just the outage


class OwOHealth(commands.Cog):
    """Periodically sends `owo ping` and reads OwO's own reported latency.

    OwO answers with something like `🏓 | ...pong! In 42ms`. When that number
    climbs past LATENCY_THRESHOLD_MS — or when no reply arrives at all — OwO is
    lagging/down, so keeping the farm running just burns commands into a dead
    bot. A single bad ping only triggers quick re-checks every 5-8s
    (CONFIRM_INTERVAL_S); after FAIL_STREAK bad pings in a row the account is
    paused and a webhook alert is pushed.

    The ping loop keeps running while the account is paused *by this cog* —
    every 15-30s (RECOVERY_INTERVAL_S) instead of every few minutes — so a
    recovered OwO un-pauses it quickly. It never pings while the
    account is paused for any other reason (captcha, ban, manual .stop).
    """

    PONG_PATTERN = re.compile(r'pong!?\s*in\s*(\d+(?:\.\d+)?)\s*ms', re.IGNORECASE)

    def __init__(self, bot):
        self.bot = bot
        self.task = None
        self.waiter = None
        self.fail_count = 0
        self.paused_by_me = False
        self.last_latency = None

    def cog_unload(self):
        if self.task and not self.task.done():
            self.task.cancel()

    async def register_actions(self):
        # register_actions also runs on every live settings save, so drop any
        # previous loop first instead of stacking a second pinger.
        if self.task and not self.task.done():
            self.task.cancel()
            self.task = None

        self.task = asyncio.create_task(self._monitor_loop())
        self.bot.log("SYS", f"OwO health monitor started (ping every {INTERVAL_MINUTES} min).")

    def _next_wait(self):
        if self.paused_by_me:
            return random.uniform(*RECOVERY_INTERVAL_S)
        if self.fail_count > 0:
            return random.uniform(*CONFIRM_INTERVAL_S)
        minutes = random.choice(INTERVAL_MINUTES)
        return max(30.0, minutes * 60 + random.uniform(-INTERVAL_JITTER_S, INTERVAL_JITTER_S))

    async def _monitor_loop(self):
        await self.bot.wait_until_ready()
        while self.bot.active:
            await asyncio.sleep(self._next_wait())

            if self.bot.stats.get('captcha_active') or (self.bot.paused and not self.paused_by_me):
                # a half-finished confirmation streak is stale once someone
                # else holds the pause; start fresh when farming resumes
                self.fail_count = 0
                continue

            try:
                await self._check_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.bot.log("ERROR", f"OwO health check failed: {e}")

    async def _check_once(self):
        self.waiter = asyncio.get_running_loop().create_future()
        try:
            if not await self._send_ping():
                return

            try:
                latency = await asyncio.wait_for(self.waiter, timeout=RESPONSE_TIMEOUT_S)
            except asyncio.TimeoutError:
                latency = None
        finally:
            self.waiter = None

        self.last_latency = latency

        if latency is None:
            await self._on_bad(f"No reply to `{self.bot.prefix}ping` within {RESPONSE_TIMEOUT_S}s")
        elif latency > LATENCY_THRESHOLD_MS:
            await self._on_bad(f"OwO latency {latency:.0f}ms (threshold {LATENCY_THRESHOLD_MS}ms)")
        else:
            await self._on_good(latency)

    async def _send_ping(self):
        """Send the ping through the same lock/interval guard send_message uses,
        but via _send_safe directly so it still works while we hold the pause."""
        content = f"{self.bot.prefix}ping"
        async with self.bot.command_lock:
            elapsed = time.time() - self.bot.last_sent_time
            if elapsed < self.bot.min_command_interval:
                await asyncio.sleep(self.bot.min_command_interval - elapsed)
            self.bot.last_sent_command = content
            self.bot.last_sent_time = time.time()
            return await self.bot._send_safe(content, skip_typing=True)

    async def _on_bad(self, reason):
        self.fail_count += 1
        self.bot.log("WARN", f"OwO health: {reason} ({self.fail_count}/{FAIL_STREAK})")

        if self.fail_count < FAIL_STREAK or self.bot.paused:
            return

        self.bot.paused = True
        self.paused_by_me = True
        self.bot.log("ALARM", f"OwO appears DOWN — account paused. {reason}")

        if AUTO_RESUME:
            tail = f"It will resume by itself once `{self.bot.prefix}ping` is healthy again."
        else:
            tail = "Resume manually with `.start`."
        await self._alert(
            "OWO BOT DOWN — ACCOUNT PAUSED",
            f"{reason}\n\nFarming has been paused automatically. {tail}"
        )

    async def _on_good(self, latency):
        had_failures = self.fail_count > 0
        self.fail_count = 0

        if not self.paused_by_me:
            if had_failures:
                self.bot.log("INFO", f"OwO health OK again ({latency:.0f}ms)")
            return

        if not self.bot.paused:
            # someone already resumed it manually (.start / dashboard)
            self.paused_by_me = False
            return

        if not AUTO_RESUME:
            return

        self.paused_by_me = False
        # Never fight the security cog for the pause: a captcha that landed while
        # we were paused must keep the account down.
        if self.bot.stats.get('captcha_active') or self.bot.stats.get('captcha_status') == 'pending':
            self.bot.log("WARN", "OwO recovered but captcha is pending — staying paused.")
            return

        self.bot.paused = False
        self.bot.throttle_until = 0
        self.bot.log("SUCCESS", f"OwO recovered ({latency:.0f}ms) — farming resumed.")

        if ALERT_ON_RECOVER:
            await self._alert(
                "OWO BACK ONLINE — RESUMED",
                f"OwO replied in {latency:.0f}ms. Farming has been resumed automatically.",
                color=0x3BA55D
            )

    async def _alert(self, title, message, color=0xFF3B3B):
        """Post to the same Discord webhook / Telegram chat the security alerts use.

        The payload is built here rather than reusing Security._send_webhook_single
        because that helper hardcodes a captcha-specific footer.
        """
        security = self.bot.get_cog("Security")
        if security:
            try:
                await security._send_telegram_async(title, message)
            except Exception as e:
                self.bot.log("ERROR", f"OwO health telegram alert failed: {e}")

        wh_cfg = self.bot.config.get('security', {}).get('webhook', {})
        if not wh_cfg.get('enabled', True):
            return
        url = wh_cfg.get('url')
        if not url:
            return

        mention_id = wh_cfg.get('mention_user_id') or getattr(self.bot, 'user_id', None)
        payload = {
            "content": f"<@{mention_id}>" if mention_id else "@here",
            "allowed_mentions": {"parse": ["users", "everyone"]},
            "embeds": [{
                "title": title,
                "description": message,
                "color": color,
                "author": {"name": f"NeuraSelf Health - {self.bot.username}"},
                "footer": {"text": f"NeuraSelf • Account: {self.bot.username} • OwO health monitor"},
                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S')
            }]
        }
        try:
            if self.bot.session:
                async with self.bot.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)):
                    pass
        except Exception as e:
            self.bot.log("ERROR", f"OwO health webhook failed: {e}")

    @commands.Cog.listener()
    async def on_message(self, message):
        waiter = self.waiter
        if waiter is None or waiter.done():
            return
        if str(message.author.id) != str(self.bot.owo_bot_id):
            return
        if message.channel.id != self.bot.channel_id:
            return

        match = self.PONG_PATTERN.search(self.bot.get_full_content(message))
        if not match:
            return

        waiter.set_result(float(match.group(1)))


async def setup(bot):
    await bot.add_cog(OwOHealth(bot))
