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

from discord.ext import commands
import json
import os
import asyncio
import time
import random
import re
import datetime

# OwO's "daily" reward resets on a fixed clock time (14:00 Vietnam/UTC+7), not
# 24h after the last claim. Scheduling off a rolling 24h window drifts away from
# the real reset and can leave the command claimable-but-unsent for a long time.
DAILY_RESET_HOUR_VN = 14
VN_TZ = datetime.timezone(datetime.timedelta(hours=7))

class Daily(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active = True
        self.stats_file = 'data/stats_daily.json'
        self.last_run = self._load_last_run()
        self.last_daily_sent = 0

    def _most_recent_reset_ts(self, ref=None):
        ref = ref if ref is not None else time.time()
        now_vn = datetime.datetime.fromtimestamp(ref, tz=VN_TZ)
        reset_today = now_vn.replace(hour=DAILY_RESET_HOUR_VN, minute=0, second=0, microsecond=0)
        if now_vn < reset_today:
            reset_today -= datetime.timedelta(days=1)
        return reset_today.timestamp()

    def _next_reset_ts(self, ref=None):
        return self._most_recent_reset_ts(ref) + 86400

    def _load_last_run(self):
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r') as f:
                    data = json.load(f)
                    return data.get(str(self.bot.user_id), 0)
            except:
                return 0
        return 0

    def _save_last_run(self, ts):
        data = {}
        if os.path.exists(self.stats_file):
            try:
                with open(self.stats_file, 'r') as f:
                    data = json.load(f)
            except:
                pass
        data[str(self.bot.user_id)] = ts
        try:
            with open(self.stats_file, 'w') as f:
                json.dump(data, f, indent=4)
        except:
            pass

    def trigger_action(self):
        self.bot.log("INFO", "Sending daily command...")
        self.last_daily_sent = time.time()
        self.last_run = time.time()
        self._save_last_run(self.last_run)

        # Assume success and aim for the next fixed reset; if OwO actually replies
        # with a "wait" (already claimed elsewhere), _process_response overrides this
        # with the exact remaining time OwO reports.
        self.cooldown = max(10, self._next_reset_ts() - time.time())

        if 'daily' in self.bot.cmd_states:
             self.bot.cmd_states['daily']['delay'] = self.cooldown

    async def register_actions(self):
        cfg = self.bot.config.get('commands', {}).get('daily', {})
        if cfg.get('enabled', False):
            last_run = self._load_last_run()
            most_recent_reset = self._most_recent_reset_ts()

            if last_run >= most_recent_reset:
                # Already claimed since the last 14:00 VN reset -> wait for the next one.
                delay = self._next_reset_ts() - time.time()
            else:
                # Haven't claimed since the last reset -> free to send now.
                delay = 3

            await self.bot.neura_register_command("daily", "daily", priority=4, delay=max(10, delay), initial_offset=0)

    @commands.Cog.listener()
    async def on_message(self, message):
        await self._process_response(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        await self._process_response(after)

    async def _process_response(self, message):
        core_config = self.bot.config.get('core', {})
        monitor_id = str(core_config.get('monitor_bot_id', '408785106942164992'))
        if str(message.author.id) != monitor_id: return
        if self.bot.owo_user is None:
            self.bot.owo_user = message.author
            
        all_channels = [str(c) for c in self.bot.channels]

        if str(message.channel.id) not in all_channels:
            return
        
        full_content = self.bot.get_full_content(message)
        if not self.bot.is_message_for_me(message): return
        
        if "wait" in full_content:
            h_match = re.search(r'(\d+)\s*[hH]', full_content)
            m_match = re.search(r'(\d+)\s*[mM]', full_content)
            s_match = re.search(r'(\d+)\s*[sS]', full_content)
            
            h = int(h_match.group(1)) if h_match else 0
            m = int(m_match.group(1)) if m_match else 0
            s = int(s_match.group(1)) if s_match else 0
            total_seconds = (h * 3600) + (m * 60) + s
            
            if total_seconds > 0:
                time_since_last = time.time() - self.last_daily_sent
                is_for_daily = (
                    "daily" in full_content or 
                    (time_since_last < 20.0) 
                )
                
                if is_for_daily:
                    self.cooldown = total_seconds + random.randint(10, 30)
                    self.last_run = time.time()
                    self._save_last_run(self.last_run)
                    self.bot.log("COOLDOWN", f"Daily wait synced: {h}h {m}m {s}s remaining.")
                    
                    if 'daily' in self.bot.cmd_states:
                        self.bot.cmd_states['daily']['delay'] = self.cooldown
                        self.bot.cmd_states['daily']['last_ran'] = time.time()

                    self.last_daily_sent = 0 

async def setup(bot):
    cog = Daily(bot)
    await bot.add_cog(cog)
