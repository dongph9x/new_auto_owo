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
import json
import os
import time
import random
import asyncio
import re
import sys
import requests
from modules.neura_human import NeuraHuman
from modules.neura_logs import neura_logger
from modules.identity import IdentityManager
from modules.interactions import setup_interactions
from modules.captcha_solver import setup_solver
from modules.web_solver import setup_web_solver
import core.state as state
import aiohttp
import unicodedata
import logging
from rich.console import Console
from rich.align import Align

_log = logging.getLogger(__name__)

class NeuraBot(commands.Bot):
    def __init__(self, token=None, channels=None):
        self.session = None
        self.base_dir = state.BASE_DIR
        self.config_file = os.path.join(state.CONFIG_DIR, 'settings.json')
        
        self.console = Console()
        self.aliases = {}
        self.config = {}
        self.accounts = []
        self.token = token
        self.channels = channels or []
        self.channels = channels or []
        self._load_config()
        
        if not self.token or not self.channels:
            if self.accounts:
                primary = self.accounts[0]
                self.token = self.token or primary.get('token')
                self.channels = self.channels or primary.get('channels', [])
        
        self.channel_id = int(self.channels[0]) if self.channels else None
        
        core_cfg = self.config.get('core', {})
        self.prefix = core_cfg.get('prefix', 'owo ')
        self.user_id = core_cfg.get('user_id')
        self.owo_bot_id = str(core_cfg.get('monitor_bot_id', '408785106942164992'))
        self.owo_user = None
        
        super().__init__(command_prefix=self.prefix, self_bot=True, enable_debug_events=True)
        
        self.username = "Bot"
        self.display_name = "Bot"
        self.nickname = None
        self.identifiers = []
        self.identity = IdentityManager(self)
        self.modules = {}
        self.active = True
        self.paused = False
        self.warmup_until = time.time() + 10
        self.throttle_until = 0.0
        self.last_sent_time = 0
        self.last_sent_command = ""
        self.command_lock = asyncio.Lock()
        self.min_command_interval = 2.2
        self.command_history = []
        self.is_ready = False
        self.cmd_cooldowns = {}
        self.cmd_states = {}
        self.neura_queue = asyncio.PriorityQueue()
        self.neura_scheduler_task = None
        self.is_busy = False

        
        self.is_mobile = "TERMUX_VERSION" in os.environ or "com.termux" in os.environ.get("PREFIX", "")
        platform = "Mobile (Termux)" if self.is_mobile else "Desktop"
        _log.info(f"Initialized bot on platform: {platform}")
        
    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        self.interactions = setup_interactions(self)
        self.captcha_solver = setup_solver(self)
        self.web_solver = setup_web_solver(self)
        self.log("SYS", "Initializing systems...")
        
        try:
            history = state.ht.load_history()
            state.ht.start_session(history)
        except Exception as e:
            self.log("ERROR", f"Failed to start history session: {e}")

        asyncio.create_task(self._process_pending_commands())
        asyncio.create_task(self.neura_queue_worker())
        self.neura_scheduler_task = asyncio.create_task(self.neura_scheduler_worker())
        await self._load_cogs()
    
    async def _process_pending_commands(self):
        await asyncio.sleep(5)
        while True:
            if not self.is_ready:
                await asyncio.sleep(1)
                continue
            
            st = self.stats
            if 'pending_commands' in st and st['pending_commands']:
                pending = st['pending_commands'][:]
                for cmd_data in pending:
                    if time.time() - cmd_data['timestamp'] < 300:
                        success = await self.send_message(cmd_data['command'])
                        if success:
                            st['pending_commands'] = [
                                c for c in st['pending_commands'] 
                                if c['timestamp'] != cmd_data['timestamp']
                            ]
                    else:
                        st['pending_commands'] = [
                            c for c in st['pending_commands'] 
                            if c['timestamp'] != cmd_data['timestamp']
                        ]
            await asyncio.sleep(2)
    
    def get_startup_delay(self, offset=0):
        return random.uniform(5, 15) + offset

    async def on_ready(self):
        if getattr(self, '_already_ready', False):
            _log.info(f"Reconnected as {self.user.name}")
            return

        self.user_id = str(self.user.id)
        self.username = self.user.name
        self.display_name = self.user.display_name
        self.user_display_name = self.display_name
        
        self.identifiers = [
            self.username.lower(),
            self.display_name.lower(),
            f"<@{self.user_id}>",
            f"<@!{self.user_id}>"
        ]

        if self.user_id not in state.account_stats:
            state.account_stats[self.user_id] = state.get_empty_stats()
        
        st = state.account_stats[self.user_id]
        st['username'] = self.username
        
        self._load_config()

        if not st.get('uptime_start'):
            st['uptime_start'] = time.time()
        
        for counter in ['hunt_count', 'battle_count', 'owo_count', 'total_cmd_count', 'other_count', 'captchas_solved', 'bans_detected', 'warnings_detected']:
            if counter not in st: st[counter] = 0
            
        if 'cowoncy_history' not in st: st['cowoncy_history'] = []
        
        self.log("SYS", f"Ready as {self.username} (Display: {self.display_name})")
        
        self.cmd_states.clear()
        
        for cog in self.cogs.values():
            if hasattr(cog, 'register_actions'):
                try:
                    await cog.register_actions()
                except Exception as e:
                    self.log("ERROR", f"Failed to register {type(cog).__name__} actions: {e}")

        active_cmds = [f"{k}({v['delay']}s)" for k, v in self.cmd_states.items()]
        self.log("DEBUG", f"Active Scheduler: {', '.join(active_cmds) if active_cmds else 'None'}")
        
        self.interactions = setup_interactions(self)
        self.captcha_solver = setup_solver(self)
        self.web_solver = setup_web_solver(self)
        
        self.log("INFO", f"Channel: {self.channel_id}")
        
        self.is_ready = True
        self._already_ready = True
        
        if self.session is None:
            self.session = aiohttp.ClientSession()
    
    async def _send_safe(self, content, skip_typing=False):
        if not content or not self.is_ready:
            return False
            
        content = self._fix_command(content)
        current_time = time.time()
        
        if current_time < self.warmup_until:
             await asyncio.sleep(max(0.1, self.warmup_until - current_time))

        if current_time < self.throttle_until:
            wait = self.throttle_until - current_time
            self.log("INFO", f"Safety Pause: Resuming in {round(wait, 1)}s (Waiting for OwO Slow-Down)")
            await asyncio.sleep(wait + 0.1)
            
        channel = self.get_channel(self.channel_id)
        if not channel:
            try:
                channel = await self.fetch_channel(self.channel_id)
            except Exception as e:
                self.log("ERROR", f"Failed to fetch channel {self.channel_id}: {e}")
                return False
        
        if not channel: return False
        
        try:
            stealth = self.config.get('stealth', {}).get('typing', {})
            if stealth.get('enabled', False) and not skip_typing:
                sent_ok = await NeuraHuman.neura_send(self, channel, content)
                if not sent_ok: return False
            else:
                await channel.send(content)
                
            short_cmd = content[:30] + "..." if len(content) > 30 else content
            self.log("CMD", f"Sent: {short_cmd}")
            return True
        except Exception as e:
            self.log("ERROR", f"Send failed: {str(e)}")
            return False
    
    def _fix_command(self, command):
        cmd = command.strip()
        if cmd.lower() == "owo": return "owo"
        if cmd.lower().startswith("owo owo"): cmd = cmd[4:]
        
        if self.shortforms:
            parts = cmd.split()
            if parts:
                base_cmd = parts[0].lower()
                prefix = self.prefix.lower()
                
                actual_cmd = base_cmd[len(prefix):] if base_cmd.startswith(prefix) else base_cmd
                
                if actual_cmd in self.shortforms:
                    if self.config.get('commands', {}).get(actual_cmd, {}).get('use_shortform', False):
                        new_base = self.shortforms[actual_cmd]
                        parts[0] = f"{self.prefix}{new_base}" if base_cmd.startswith(prefix) else new_base
                        cmd = " ".join(parts)

        known = ['hunt', 'battle', 'curse', 'huntbot', 'daily', 'cookie',
                'quest', 'checklist', 'cf', 'slots', 'autohunt', 'upgrade',
                'sacrifice', 'team', 'zoo', 'use', 'inv', 'sell', 'crate',
                'lootbox', 'run', 'pup', 'piku','pray']
        
        if self.shortforms:
            for sf in self.shortforms.values():
                if sf not in known:
                    known.append(sf)

        first = cmd.lower().split()[0] if cmd else ""
        if first in known and not cmd.lower().startswith(self.prefix.lower()):
            return f"{self.prefix}{cmd}"
        return cmd
    
    async def send_message(self, content, skip_typing=False, priority=False):
        if not self.active: return False
        if self.paused and "autohunt" not in content.lower() and "check" not in content.lower():
            return False
        
        wait_limit = 1.2 if priority else self.min_command_interval
        
        async with self.command_lock:
            now = time.time()
            elapsed = now - self.last_sent_time
            if elapsed < wait_limit:
                await asyncio.sleep(wait_limit - elapsed)
            
            if state.checking_gems.get(self.user_id):
                cmd_clean = content.lower().strip()
                if "hunt" in cmd_clean or "battle" in cmd_clean:
                    if "huntbot" not in cmd_clean and "autohunt" not in cmd_clean:
                        return False

            fixed_content = self._fix_command(content)
            self.last_sent_command = fixed_content
            self.last_sent_time = time.time()
            
            success = await self._send_safe(fixed_content, skip_typing=skip_typing)
            return success
    
    @property
    def stats(self):
        if not hasattr(self, '_connection') or not self.user: return {}
        uid = str(self.user.id)
        if uid not in state.account_stats:
            state.account_stats[uid] = state.get_empty_stats()
            state.account_stats[uid]['username'] = self.username
        return state.account_stats[uid]

    def log(self, log_type, message):
        neura_logger.log(self, log_type, message)

    async def _load_cogs(self):
        cogs_dir = os.path.join(self.base_dir, 'cogs')
        for filename in os.listdir(cogs_dir):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    self.log("SYS", f"Loaded {filename}")
                except Exception as e:
                    self.log("ERROR", f"Failed to load {filename}: {e}")
    
    async def sync_settings(self, new_config):
        """Perform a deep merge of new_config and rebuild the command scheduler."""
        self._load_config()
        self._deep_merge(self.config, new_config)
        
        core_cfg = self.config.get('core', {})
        self.prefix = core_cfg.get('prefix', 'owo ')
        if hasattr(self, '_connection'):
            self.command_prefix = self.prefix

        self.cmd_states.clear()
        
        for cog in self.cogs.values():
            if hasattr(cog, 'register_actions'):
                try:
                    await cog.register_actions()
                except Exception as e:
                    self.log("ERROR", f"Failed to re-register {cog.__class__.__name__}: {e}")
        
        active_cmds = [f"{k}({v['delay']}s)" for k, v in self.cmd_states.items()]
        self.log("SYS", f"Settings synced. Active Scheduler: {', '.join(active_cmds) if active_cmds else 'None'}")

    def _deep_merge(self, base, override):
        for key, value in override.items():
            if isinstance(value, dict) and key in base and isinstance(base[key], dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def _load_config(self):
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r') as f:
                    self.config = json.load(f)
            else:
                self.config = {}

            uid = getattr(self, 'user_id', None)
            if not uid and hasattr(self, '_connection') and self.user:
                uid = str(self.user.id)
            
            if uid:
                user_config_file = os.path.join(state.CONFIG_DIR, f'settings_{uid}.json')
                
                if os.path.exists(user_config_file):
                    try:
                        with open(user_config_file, 'r') as f:
                            user_cfg = json.load(f)
                            self._deep_merge(self.config, user_cfg)
                        self.log("SYS", f"Using account-specific settings: settings_{uid}.json")
                    except Exception as e:
                        self.log("ERROR", f"Failed to load user settings_{uid}.json: {e}")
                else:
                    try:
                        with open(user_config_file, 'w') as f:
                            json.dump(self.config, f, indent=4)
                        self.log("SYS", f"Created personal settings file: settings_{uid}.json")
                    except Exception as e:
                        self.log("ERROR", f"Failed to create settings_{uid}.json: {e}")
            else:
                self.log("SYS", "Using global settings: settings.json")

            account_file = os.path.join(self.base_dir, 'config', 'accounts.json')
            if os.path.exists(account_file):
                try:
                    with open(account_file, 'r') as f:
                        self.accounts = json.load(f).get('accounts', [])
                except:
                    self.accounts = []
            else:
                self.accounts = []

            if self.accounts:
                current_acc = None
                if uid:
                    current_acc = next((a for a in self.accounts if str(a.get('id', a.get('user_id', ''))) == uid), None)
                if not current_acc and self.token:
                    current_acc = next((a for a in self.accounts if a.get('token') == self.token), None)
                
                if current_acc:
                    new_channels = current_acc.get('channels', [])
                    if new_channels != self.channels:
                        self.channels = new_channels
                        if self.channels:
                            if str(self.channel_id) not in [str(c) for c in self.channels]:
                                self.channel_id = int(self.channels[0])
                                self.log("SYS", f"Channel rotated to {self.channel_id} (Config Update)")
                        self.log("SYS", f"Channels updated from accounts.json: {len(self.channels)} available")
                
                elif not self.channels:
                    primary = self.accounts[0]
                    self.channels = primary.get('channels', [])
                    self.channel_id = int(self.channels[0]) if self.channels else None

            shortform_file = os.path.join(self.base_dir, 'config', 'shortform.json')
            if os.path.exists(shortform_file):
                try:
                    with open(shortform_file, 'r') as f:
                        self.shortforms = json.load(f)
                except:
                    self.shortforms = {}
            else:
                self.shortforms = {}

            core_cfg = self.config.get('core', {})
            self.prefix = core_cfg.get('prefix', 'owo ')
            if hasattr(self, '_connection'):
                self.command_prefix = self.prefix

        except Exception as e:
            print(f"Error loading config: {e}")
            self.config = {}


    def check_version(self):
        CURRENT_VERSION = "2.3.2" 
        VERSION_URL = "https://raw.githubusercontent.com/routo-loop/neura_status_api/main/version.json"
        
        self.log("SYS", "Checking for updates...")
        try:
            r = requests.get(VERSION_URL, timeout=5)
            if r.status_code == 200:
                data = r.json()
                latest_version = data.get("version", "2.3.0")
                changelog = data.get("changelog", "No changes listed.")
                
                if latest_version != CURRENT_VERSION:
                    os.system('cls' if os.name == 'nt' else 'clear')
                    line = "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈"
                    self.console.print("\n")
                    self.console.print(Align.center(f"[bold red]{line}[/bold red]"))
                    self.console.print(Align.center(f"[bold white]   NEW VERSION AVAILABLE: [yellow]{latest_version}[/yellow] (Current: {CURRENT_VERSION})[/bold white]"))
                    self.console.print(Align.center(f"[bold red]{line}[/bold red]"))
                    self.console.print(Align.center(f"\n[bold cyan]CHANGELOG:[/bold cyan]\n[white]{changelog}[/white]\n"))
                    self.console.print(Align.center(f"[bold red]{line}[/bold red]"))
                    self.console.print(Align.center("[bold yellow]PLEASE UPDATE TO CONTINUE:[/bold yellow]"))
                    self.console.print(Align.center("[bold cyan]https://github.com/routo-loop/neura-self[/bold cyan]"))
                    self.console.print(Align.center(f"[bold red]{line}[/bold red]"))
                    self.console.print("\n")
                    sys.exit(0)
                else:
                    self.log("SYS", "You are on the latest version.")
        except Exception as e:
            self.log("WARN", f"Version check failed: {e}")
    
    async def run_bot(self):
        self.check_version()
        self.log("SYS", "Starting bot...")
        await self.start(self.token)

    def set_cooldown(self, cmd, seconds):
        self.cmd_cooldowns[cmd.lower()] = time.time() + seconds

    def get_cooldown(self, cmd):
        return max(0, self.cmd_cooldowns.get(cmd.lower(), 0) - time.time())


    def get_full_content(self, message):
        if not message: return ""
        content = message.content or ""
        embed_texts = []
        if message.embeds:
            for em in message.embeds:
                parts = [
                    em.title or "",
                    em.author.name if em.author else "",
                    em.description or "",
                    "\n".join([f"{f.name}: {f.value}" for f in em.fields])
                ]
                embed_texts.append("\n".join([p for p in parts if p]))
        return (content + "\n" + "\n".join(embed_texts)).lower()


    def is_message_for_me(self, message, role="any", keyword=None):
        return self.identity.is_message_for_me(message, role, keyword)

    async def neura_enqueue(self, content, priority=3, skip_typing=None, _cmd_id=None):
        options = {"skip_typing": skip_typing, "_cmd_id": _cmd_id}
        item = (priority, time.time(), content, options)
        await self.neura_queue.put(item)

    async def neura_queue_worker(self):
        await self.wait_until_ready()
        self.log("SYS", "NeuraQueue Worker started.")
        while self.active:
            try:
                priority, ts, content, options = await self.neura_queue.get()
                cmd_id = options.get("_cmd_id")

                ran_successfully = False
                
                try:
                    if content == "":
                        if cmd_id == "channelswitch":
                            cog = self.get_cog("ChannelSwitch")
                            if cog: cog.trigger_switch()
                        
                        if cmd_id and cmd_id in self.cmd_states:
                           self.cmd_states[cmd_id]['last_ran'] = time.time()
                        
                        ran_successfully = True
                        continue
                    
                    wait_limit = 1.2 if priority <= 1 else self.min_command_interval
                    
                    now = time.time()
                    elapsed = now - self.last_sent_time
                    if elapsed < wait_limit:
                        await asyncio.sleep(wait_limit - elapsed)

                    if self.paused and "autohunt" not in content.lower() and "check" not in content.lower():
                        continue

                    gem_check_val = state.checking_gems.get(self.user_id)
                    if gem_check_val:
                        timestamp = gem_check_val.get("time") if isinstance(gem_check_val, dict) else (time.time() if isinstance(gem_check_val, bool) else gem_check_val)
                        
                        if timestamp and time.time() - timestamp > 20:
                            self.log("WARN", "NeuraGems check timed out. Resuming queue.")
                            state.checking_gems[self.user_id] = False
                            gem_check_val = False
                    
                    if gem_check_val:
                        cmd_clean = content.lower().strip()
                        if "hunt" in cmd_clean or "battle" in cmd_clean:
                             if "huntbot" not in cmd_clean and "autohunt" not in cmd_clean:
                                continue

                    skip_typing = options.get("skip_typing")
                    if skip_typing is None:
                        skip_typing = priority <= 1 or content.lower().strip() == "owo"

                    if cmd_id and cmd_id in self.cmd_states:
                        last_ran = self.cmd_states[cmd_id]['last_ran']
                        if time.time() - last_ran < 2.0:
                            continue
                        
                        self.cmd_states[cmd_id]['last_ran'] = time.time()

                    await self._send_safe(content, skip_typing=skip_typing)
                    self.last_sent_time = time.time()
                    ran_successfully = True
                    
                    if cmd_id and cmd_id in self.cmd_states:
                        if cmd_id in ["rpp", "quest", "level_quotes", "huntbot", "daily", "cookie", "coinflip", "slots"]:
                            class_map = {
                                "rpp": "RPP", "quest": "Quest", "level_quotes": "LevelQuotes", 
                                "huntbot": "HuntBot", "daily": "Daily", "cookie": "Cookie",
                                "coinflip": "Gambling", "slots": "Gambling"
                            }
                            
                            cog = self.get_cog(class_map[cmd_id])
                            if cog:
                                if cmd_id == "coinflip": getattr(cog, "trigger_coinflip")()
                                elif cmd_id == "slots": getattr(cog, "trigger_slots")()
                                else: getattr(cog, "trigger_action")()
                
                finally:
                    if cmd_id and cmd_id in self.cmd_states:
                        self.cmd_states[cmd_id]['in_queue'] = False
                    self.neura_queue.task_done()

            except Exception as e:
                self.log("ERROR", f"Queue worker error: {e}")
                await asyncio.sleep(1)

    async def neura_register_command(self, cmd_id, content, priority, delay, initial_offset=0):
        self.cmd_states[cmd_id] = {
            "content": content,
            "priority": priority,
            "delay": delay,
            "last_ran": time.time() - delay + initial_offset,
            "in_queue": False
        }

    async def neura_scheduler_worker(self):
        await self.wait_until_ready()
        self.log("SYS", "NeuraScheduler started.")
        while self.active:
            try:
                if self.paused:
                    await asyncio.sleep(1)
                    continue

                now = time.time()
                for cmd_id, state in list(self.cmd_states.items()):
                    if state["in_queue"]: continue
                    
                    if now - state["last_ran"] >= state["delay"]:
                        state["in_queue"] = True
                        actual_content = state["content"]
                        if callable(actual_content):
                            if asyncio.iscoroutinefunction(actual_content):
                                actual_content = await actual_content()
                            else:
                                actual_content = actual_content()
                        
                        if actual_content is not None:
                            asyncio.create_task(self.neura_enqueue(actual_content, priority=state["priority"], _cmd_id=cmd_id))
                        else:
                            state["in_queue"] = False
                            state["last_ran"] = time.time()

                await asyncio.sleep(1)
            except Exception as e:
                self.log("ERROR", f"Scheduler error: {e}")
                import traceback
                traceback.print_exc()
                await asyncio.sleep(1)
