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

import discord
from discord.ext import commands
import asyncio
import re
import time
import random
import core.state as state

class ResponseHandler(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_success_time = {}
        self.success_triggers = {
            'hunt': ['you found:', 'you found', 'found:', 'is empowered by'],
            'battle': ['you won', 'you lost', 'goes into battle', 'battle!', 'won in', 'lost in', 'team gained', 'streak:', 'battle team gained', 'battle goes into', 'you won in', 'you lost in'],
            'curse': ['puts a curse on', 'is cursed', 'ghostly curse'],
            'pray': ['prays for', 'prays...'],
            'cookie': ['gave a cookie to', 'sent a cookie'],
            'daily': ['collected your daily', 'daily reward']
        }

    @commands.Cog.listener()
    async def on_message(self, message):
        await self._process_response(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        await self._process_response(after)

    async def _process_response(self, message):
        if message.author.id == self.bot.user.id: return
        core_config = self.bot.config.get('core', {})
        monitor_id = str(core_config.get('monitor_bot_id', '408785106942164992'))
        if str(message.author.id) != monitor_id: return
        
        if self.bot.owo_user is None:
            self.bot.owo_user = message.author
        all_channels = [str(c) for c in self.bot.channels]
        if str(message.channel.id) not in all_channels:
            return
        

        full_content = self.bot.get_full_content(message)
        await self._handle_cooldowns(full_content, message)
        
        await self._handle_battle_results(full_content, message)
        
        if self.bot.is_message_for_me(message):
            await self._handle_success(full_content, message)
            await self._handle_status_updates(full_content, message)

    async def _handle_success(self, content, message):
        now = time.time()
        for cmd_type, triggers in self.success_triggers.items():
            if cmd_type == 'battle': continue 
            for trigger in triggers:
                if trigger in content:
                    if now - self.last_success_time.get(cmd_type, 0) < 5.0: break
                    self.last_success_time[cmd_type] = now
                    
                    if cmd_type == 'hunt':
                        self.bot.stats['hunt_count'] = self.bot.stats.get('hunt_count', 0) + 1
                        self.bot.log("SUCCESS", f"Hunt confirmed for {self.bot.display_name}")
                    elif cmd_type == 'curse':
                        if self.bot.is_message_for_me(message, role="source", keyword="puts a curse on"):
                            self.bot.log("SUCCESS", f"Curse confirmed for {self.bot.display_name}")
                        else: continue
                    elif cmd_type == 'pray':
                        if self.bot.is_message_for_me(message, role="source", keyword="prays for"):
                            self.bot.log("SUCCESS", f"Pray confirmed for {self.bot.display_name}")
                        else: continue
                    elif cmd_type == 'cookie':
                        if self.bot.is_message_for_me(message, role="target", keyword="got a cookie from"):
                            self.bot.log("SUCCESS", f"Cookie confirmed for {self.bot.display_name}")
                        else: continue

    async def _handle_battle_results(self, content, message):
        is_battle_msg = any(trigger in content for trigger in ['goes into battle', 'battle!', 'won in', 'lost in', 'streak:', 'you won', 'you lost'])
        if not is_battle_msg: return

        is_for_me = self.bot.is_message_for_me(message)
        
        if is_for_me:
            now = time.time()
            if now - self.last_success_time.get('battle', 0) > 5.0:
                self.last_success_time['battle'] = now
                self.bot.stats['battle_count'] = self.bot.stats.get('battle_count', 0) + 1
                self.bot.log("SUCCESS", f"Battle confirmed for {self.bot.display_name}")
        else:
            pass

    async def _handle_cooldowns(self, content, message):
        if "slow down~" in content or "too fast for me" in content:
            wait_time = random.uniform(3.0, 5.0)
            self.bot.throttle_until = time.time() + wait_time
            self.bot.log("COOLDOWN", f"Global Throttle: pausing {round(wait_time, 1)}s")
            return

    async def _handle_status_updates(self, content, message):
        pass

async def setup(bot):
    cog = ResponseHandler(bot)
    await bot.add_cog(cog)