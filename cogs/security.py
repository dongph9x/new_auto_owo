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

import sys
import asyncio
import time
import re
import os
import threading
import unicodedata
import requests
import aiohttp
import json
import html
from urllib.parse import quote
import discord
from discord.ext import commands
from plyer import notification
import core.state as state

class Security(commands.Cog):
    CAPTCHA_TAG_INTERVAL_SECONDS = 120
    CAPTCHA_RESOLVE_ON_REMINDER_COUNT = 5

    def __init__(self, bot):
        self.bot = bot
        self.monitor_id = str(bot.config.get('core', {}).get('monitor_bot_id', '408785106942164992'))
        self.beep_file = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "beeps", "security_beep.mp3")
        self.ban_keywords = [
            "youhavebeenbanned",
            "bannedforbotting",
            "bannedformacros"
        ]
        self.captcha_keywords = [
            "areyouarealhuman",
            "verifythatyouarehuman",
            "pleasecompletethiswithin",
            "pleaseusethelinkbelow",
            "completeyourcaptcha",
            "pleasedmmewiththefollowing",
            "pleasedmmewithonly",
            "ifyouhavetroublesolvingthecaptcha",
            "pleasecomplete",
            "tocheckthatyouareahuman",
            "tocheck",
            "human"
        ]
        self.warning_pattern = re.compile(r'\((\d+)/(\d+)\)')
        self.image_captcha_keywords = [
            "pleasedmme",
            "dmme",
            "beepboop",
            "checkthatyouareahuman",
            "solvingthecaptcha",
            "letterword"
        ]
        self._captcha_alert_task = None
        self._refresh_security_settings()

    async def register_actions(self):
        self._refresh_security_settings()
        self.monitor_id = str(self.bot.config.get('core', {}).get('monitor_bot_id', '408785106942164992'))
        self.bot.log("SYS", "Security Module settings refreshed (Live Sync).")

    def _refresh_security_settings(self):
        cfg = self.bot.config.get('security', {})
        self.enabled = cfg.get('enabled', True)
        self.notifications_enabled = cfg.get('notifications', {}).get('enabled', True)
        self.notification_title = cfg.get('notifications', {}).get('desktop', {}).get('title', "Neura Security Alert")
        tg_cfg = cfg.get('telegram', {})
        self.telegram_enabled = tg_cfg.get('enabled', False)
        self.telegram_token = str(tg_cfg.get('token', '') or '').strip()
        self.telegram_chat_id = str(tg_cfg.get('chat_id', '') or '').strip()

    def _normalize(self, text):
        if not text:
            return ""
        text = unicodedata.normalize("NFKD", text)
        return re.sub(r'[^a-zA-Z0-9]', '', text.lower())

    def _show_desktop_notification(self, message):
        if not self.notifications_enabled:
            return
        sec_cfg = self.bot.config.get('security', {})
        notif_cfg = sec_cfg.get('notifications', {})
        if self.bot.is_mobile:
            mobile = notif_cfg.get('mobile', {})
            if mobile.get('enabled', True):
                try:
                    os.system(f'termux-notification --title "{self.notification_title}" --content "{message}"')
                    vib = mobile.get('vibrate', {})
                    if vib.get('enabled', True):
                        duration = int(vib.get('time', 0.5) * 1000)
                        os.system(f'termux-vibrate -d {duration}')
                    toast = mobile.get('toast', {})
                    if toast.get('enabled', True):
                        bg = toast.get('bg_color', 'black')
                        fg = toast.get('text_color', 'white')
                        pos = toast.get('position', 'middle')
                        os.system(f'termux-toast -b {bg} -c {fg} -g {pos} "{message}"')
                    tts = mobile.get('tts', {})
                    if tts.get('enabled', False):
                        os.system(f'termux-tts-speak "{message}"')
                except:
                    pass
            return
        desktop = notif_cfg.get('desktop', {})
        if desktop.get('enabled', True):
            try:
                notification.notify(title=self.notification_title, message=message, timeout=10)
            except:
                pass
    
    def _send_webhook(self, title, message):
        """Fire-and-forget: schedules the webhook send + cross-account DM alert on the event loop."""
        asyncio.create_task(self._send_webhook_async(title, message))
        asyncio.create_task(self._send_telegram_async(title, message, repeat_count=2, repeat_interval=10))
        asyncio.create_task(self._notify_via_sibling_accounts(title, message))

    async def _send_telegram_async(self, title, message, repeat_count=1, repeat_interval=0):
        if not self.telegram_enabled:
            return
        if not self.telegram_token or not self.telegram_chat_id:
            return

        safe_title = html.escape(str(title or "Security Alert"))
        safe_message = html.escape(str(message or ""))
        account = html.escape(str(self.bot.username or "Unknown"))
        text = (
            f"<b>{safe_title}</b>\n"
            f"Account: <code>{account}</code>\n\n"
            f"{safe_message}"
        )
        if len(text) > 3800:
            text = text[:3797] + "..."

        api_url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }
        for i in range(max(1, int(repeat_count or 1))):
            try:
                if self.bot.session:
                    async with self.bot.session.post(api_url, json=payload, timeout=aiohttp.ClientTimeout(total=5)):
                        pass
                else:
                    requests.post(api_url, json=payload, timeout=5)
            except Exception as e:
                self.bot.log("ERROR", f"Telegram push failed: {e}")
                break

            if i < repeat_count - 1 and repeat_interval > 0:
                await asyncio.sleep(repeat_interval)

    async def _send_webhook_async(self, title, message):
        cfg = self.bot.config.get('security', {})
        wh_cfg = cfg.get('webhook', {})
        if not wh_cfg.get('enabled', True): return
        url = wh_cfg.get('url')
        if not url: return

        mention_id = wh_cfg.get('mention_user_id') or getattr(self.bot, 'user_id', None)
        content = f"<@{mention_id}>" if mention_id else "@here"

        repeat_count = 2
        repeat_interval = 10

        for i in range(repeat_count):
            payload = {
                "content": content,
                "allowed_mentions": {"parse": ["users", "everyone"]},
                "embeds": [{
                    "title": title,
                    "description": message,
                    "color": 0xFF3B3B,
                    "author": {
                        "name": f"NeuraSelf Security - {self.bot.username}",
                        "icon_url": "https://cdn.discordapp.com/attachments/1450161614375620802/1456632606002118657/neuralogo.png"
                    },
                    "footer": {"text": f"NeuraSelf • Account: {self.bot.username} • Alert {i + 1}/{repeat_count}"},
                    "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S')
                }]
            }
            try:
                # Use the bot's own aiohttp session (non-blocking) instead of `requests`
                # (blocking) since this now runs repeatedly over several seconds and would
                # otherwise stall the shared event loop that every account runs on.
                if self.bot.session:
                    async with self.bot.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        pass
                else:
                    requests.post(url, json=payload, timeout=5)
            except Exception:
                pass

            if i < repeat_count - 1:
                await asyncio.sleep(repeat_interval)

    async def _notify_via_sibling_accounts(self, title, message):
        """Try each other currently-running account in turn until one successfully DMs
        this account's owner about the incident — stop as soon as one gets through,
        no need to spam from every sibling once the alert has landed.
        """
        target_id = getattr(self.bot, 'user_id', None)
        if not target_id:
            return

        for other_bot in list(state.bot_instances):
            if other_bot is self.bot:
                continue
            if not (other_bot.is_ready and other_bot.user):
                continue
            try:
                user = other_bot.get_user(int(target_id)) or await other_bot.fetch_user(int(target_id))
                if user:
                    await user.send(f"**{title}** — {self.bot.username} cần xử lý!\n{message}")
                    return  # got through, no need to try the remaining siblings
            except Exception as e:
                other_bot.log("ERROR", f"Failed to DM {self.bot.username} about security alert: {e}")

    def _build_clear_link(self):
        cfg = self.bot.config.get('security', {})
        base_url = (cfg.get('dashboard_url') or 'http://localhost:8000').rstrip('/')
        uid = str(self.bot.user_id)
        token = state.make_captcha_link_token(uid, "clear_alert", 600)
        return f"{base_url}/security/clear-captcha?id={quote(uid, safe='')}&token={quote(token, safe='')}"

    def _build_verify_link(self):
        cfg = self.bot.config.get('security', {})
        base_url = (cfg.get('dashboard_url') or 'http://localhost:8000').rstrip('/')
        uid = str(self.bot.user_id)
        token = state.make_captcha_link_token(uid, "verify_captcha", 600)
        return f"{base_url}/security/verify-captcha?id={quote(uid, safe='')}&token={quote(token, safe='')}"

    async def _send_webhook_single(self, title, message, include_mention=True):
        """One-shot webhook post, used by the continuous captcha loop (which handles
        its own repeat/interval timing, so it doesn't need _send_webhook_async's
        built-in repeat)."""
        await self._send_telegram_async(title, message, repeat_count=1, repeat_interval=0)
        cfg = self.bot.config.get('security', {})
        wh_cfg = cfg.get('webhook', {})
        if not wh_cfg.get('enabled', True): return
        url = wh_cfg.get('url')
        if not url: return

        mention_id = wh_cfg.get('mention_user_id') or getattr(self.bot, 'user_id', None)
        content = (f"<@{mention_id}>" if mention_id else "@here") if include_mention else ""
        allowed_mentions = {"parse": ["users", "everyone"]} if include_mention else {"parse": []}

        payload = {
            "content": content,
            "allowed_mentions": allowed_mentions,
            "embeds": [{
                "title": title,
                "description": message,
                "color": 0xFF3B3B,
                "author": {
                    "name": f"NeuraSelf Security - {self.bot.username}",
                    "icon_url": "https://cdn.discordapp.com/attachments/1450161614375620802/1456632606002118657/neuralogo.png"
                },
                "footer": {"text": f"NeuraSelf • Account: {self.bot.username} • Đang chờ xử lý captcha"},
                "timestamp": time.strftime('%Y-%m-%dT%H:%M:%S')
            }]
        }
        try:
            if self.bot.session:
                async with self.bot.session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    pass
            else:
                requests.post(url, json=payload, timeout=5)
        except Exception:
            pass

    def _start_continuous_captcha_alert(self, title, message):
        """Keep nagging (webhook + sibling-account DM) every 2 minutes while
        captcha is still pending. The loop stops only when captcha is finalized
        as resolved or failed."""
        st = self.bot.stats
        already_active = st.get('captcha_active', False)
        st['captcha_active'] = True
        st.setdefault('captcha_status', 'pending')
        if not already_active:
            st['captcha_alert_count'] = 0

        if already_active and self._captcha_alert_task and not self._captcha_alert_task.done():
            return  # already nagging, no need for a second overlapping loop

        self._captcha_alert_task = asyncio.create_task(self._captcha_alert_loop(title, message))

    async def _captcha_alert_loop(self, title, message):
        while (
            self.bot.stats.get('captcha_active')
            and self.bot.paused
            and self.bot.stats.get('captcha_status', 'pending') == 'pending'
        ):
            next_count = int(self.bot.stats.get('captcha_alert_count', 0)) + 1
            self.bot.stats['captcha_alert_count'] = next_count
            # Generate fresh expiring tokens each loop iteration so links don't go
            # stale during long captcha incidents.
            clear_link = self._build_clear_link()
            verify_link = self._build_verify_link()
            full_message = (
                f"{message}\n\n"
                f"🔓 Link verify trực tiếp account này: {verify_link}\n"
                f"🔕 Đã xử lý xong? Bấm vào đây để tắt nhắc: {clear_link}"
            )
            await self._send_webhook_single(title, full_message, include_mention=True)
            await self._notify_via_sibling_accounts(title, full_message)
            if next_count >= self.CAPTCHA_RESOLVE_ON_REMINDER_COUNT:
                self.bot.stats['captcha_status'] = 'resolved'
                self.bot.stats['captcha_active'] = False
                self.bot.log(
                    "SECURITY",
                    f"Captcha alert reached reminder {self.CAPTCHA_RESOLVE_ON_REMINDER_COUNT}; marking resolved."
                )
                break
            await asyncio.sleep(self.CAPTCHA_TAG_INTERVAL_SECONDS)

        self.bot.stats['captcha_active'] = False

    async def _notify_captcha_failed(self, title, message, fail_reason):
        error_message = message
        if fail_reason:
            error_message += f"\n\n❌ Captcha failed: {fail_reason}"
        error_message += "\n\n⚠️ Captcha đã fail, cần kiểm tra và xử lý thủ công."
        await self._send_webhook_single(title, error_message, include_mention=True)
        await self._notify_via_sibling_accounts(title, error_message)

    async def play_beep(self):
        def _play():
            if not os.path.exists(self.beep_file):
                return
            
            if self.bot.is_mobile:
                try:
                    os.system(f'termux-media-player play "{self.beep_file}"')
                except:
                    pass
                return

            try:
                 from playsound3 import playsound
                 playsound(self.beep_file, block=False)
            except:
                pass
        threading.Thread(target=_play, daemon=True).start()

    def _contains_keyword(self, text, keywords):
        cleaned = self._normalize(text)
        return any(k in cleaned for k in keywords)

    def _get_captcha_url(self, message):
        if not message.components:
            return None
        for comp in message.components:
            if not getattr(comp, "children", None): continue
            for child in comp.children:
                url = str(getattr(child, "url", "") or "")
                if "owobot.com/captcha" in url:
                    return url
        return None


    @commands.Cog.listener()
    async def on_message(self, message):
        if not self.enabled: return
        if isinstance(message.channel, discord.DMChannel) and message.author.id == int(self.monitor_id):
            if (discord.utils.utcnow() - message.created_at).total_seconds() > 30: return
            # This is the only reliable signal that captcha is actually completed.
            # Verify-link click can stop reminder spam, but should not blindly resume.
            if "i have verified that you are human" in message.content.lower():
                self.bot.paused = False
                self.bot.throttle_until = 0.0
                self.bot.last_sent_time = 0
                self.bot.warmup_until = 0
                self.bot.stats['captcha_active'] = False
                self.bot.stats['captcha_status'] = 'resolved'

                grinding_cog = self.bot.get_cog('Grinding')
                if grinding_cog:
                    grinding_cog.cooldowns['hunt'] = 0
                    grinding_cog.cooldowns['battle'] = 0
                    grinding_cog.cooldowns['owo'] = 0

                self.bot.log("SUCCESS", "Verified detected in DM. Captcha solved successfully. Resuming...")
                self.bot.log("INFO", "All cooldowns reset. Bot will resume in 2 seconds...")
                await asyncio.sleep(2)
                return

            if "letterword" in message.content.lower() and message.attachments:
                self.bot.log("SECURITY", "Detection AI: Letterword captcha identified in DMs.")
 
                count_match = re.search(r'(\d+)\s*letterword', message.content.lower())
                letter_count = int(count_match.group(1)) if count_match else 5
                
                image_url = message.attachments[0].url

                self.bot.log("SYS", f"Attempting to solve DM Captcha ({letter_count} letters)...")
                answer = await self.bot.captcha_solver.solve_image(image_url, letter_count)
                
                if answer:
                    self.bot.log("SUCCESS", f"AI Solver Answer: {answer}. Sending to OwO...")
                    await asyncio.sleep(random.uniform(2.0, 4.0))
                    async with message.channel.typing():
                        await asyncio.sleep(len(answer) * 0.1)
                        await message.channel.send(answer)
                else:
                    self.bot.log("ERROR", "AI Solver failed to generate an answer.")
                    self._show_desktop_notification("AI Solver failed! Solve manually.")
                return

            captcha_url = self._get_captcha_url(message)
            if not captcha_url:
                url_match = re.search(r'https?://owobot\.com/captcha/\S+', message.content)
                if url_match: captcha_url = url_match.group(0)
            
            if captcha_url:
                self.bot.paused = True
                self.bot.throttle_until = time.time() + 3600
                self.bot.stats['captcha_status'] = 'pending'
                self.bot.stats['captcha_alert_count'] = 0
                self.bot.log("ALARM", "LINK CAPTCHA DETECTED IN DM!")
                await self.play_beep()
                self._show_desktop_notification("DM Captcha detected!")
                self.bot.log("SYS", "Starting priority DM/webhook captcha alert loop immediately.")
                self._start_continuous_captcha_alert("DM CAPTCHA", f"Solve link in DM: {captcha_url}")
                
                sec_cfg = self.bot.config.get("security", {})
                sol_cfg = sec_cfg.get("captcha_solver", {})

                # Who may VIEW/EDIT captcha_solver (admin dashboard session only) is enforced
                # in dashboard/app.py; any account role may USE it here once configured.
                autosolved = False
                auto_attempted = False
                fail_reason = None
                if sol_cfg.get("enabled", True) and sol_cfg.get("api_key"):
                    auto_attempted = True
                    self.bot.log("SYS", f"Attempting {self.bot.web_solver.provider} auto-solve for DM...")
                    autosolved, fail_reason = await self.bot.web_solver.auto_verify(max_total_seconds=480)
                    if autosolved:
                        self.bot.log("SUCCESS", f"{self.bot.web_solver.provider} solved successfully (DM)!")
                        self._show_desktop_notification("Captcha solved successfully!")
                        self.bot.stats['captcha_active'] = False
                        self.bot.stats['captcha_status'] = 'resolved'
                    elif self.bot.stats.get('captcha_status', 'pending') == 'pending':
                        self.bot.log("ERROR", f"{self.bot.web_solver.provider} auto-solve failed (DM): {fail_reason}")
                        self._show_desktop_notification("Auto-solve failed! Solve manually.")
                        self.bot.stats['captcha_status'] = 'failed'

                if (
                    auto_attempted
                    and not autosolved
                    and self.bot.stats.get('captcha_status', 'pending') == 'failed'
                ):
                    self.bot.log("SYS", "Auto-solve failed; sending final fail notification.")
                    alert_msg = f"Solve link in DM: {captcha_url}"
                    if fail_reason:
                        alert_msg += f"\n\n⚠️ Auto-solve error ({self.bot.web_solver.provider}): {fail_reason}"
                    diag = self.bot.web_solver.get_last_diagnostic_summary()
                    if diag:
                        alert_msg += f"\n\n🧾 Trace: {diag}"
                    self.bot.stats['captcha_active'] = False
                    await self._notify_captcha_failed("DM CAPTCHA", alert_msg, fail_reason)
                    if sys.platform == "win32" and sec_cfg.get("open_captcha_url_on_pc", False):
                        self.bot.log("SYS", "Opening Captcha in Browser with Auto-Login...")
                        asyncio.create_task(self.bot.web_solver.open_in_browser(captcha_url))

                return
        if str(message.author.id) != self.monitor_id: return
        
        if self.bot.owo_user is None:
            self.bot.owo_user = message.author
        try:
            allowed_channels = [int(ch) for ch in self.bot.channels]
        except:
            allowed_channels = [self.bot.channel_id]
            
        if message.channel.id not in allowed_channels: return
        content = message.content or ""
        embed_text = ""
        if message.embeds:
            parts = []
            for e in message.embeds:
                if e.title: parts.append(e.title)
                if e.description: parts.append(e.description)
                if e.footer and e.footer.text: parts.append(e.footer.text)
            embed_text = " ".join(parts)
        text_to_check = f"{content} {embed_text}"
        is_for_me = self.bot.is_message_for_me(message)
        if not is_for_me: return
        if self._contains_keyword(text_to_check, self.ban_keywords):
            self.bot.paused = True
            self.bot.log("ALARM", "BAN DETECTED!")
            await self.play_beep()
            self._show_desktop_notification("Ban detected!")
            self._send_webhook("BAN DETECTED", f"Message:\n{content}")
            return
        warning_match = self.warning_pattern.search(text_to_check)
        if warning_match:
            current_warning = int(warning_match.group(1))
            max_warnings = int(warning_match.group(2))
            normalized = self._normalize(text_to_check)
            if any(kw in normalized for kw in ["pleasecomplete", "captcha", "verify", "human"]):
                self.bot.paused = True
                self.bot.throttle_until = time.time() + 3600
                self.bot.stats['last_captcha_msg'] = text_to_check[:200]
                self.bot.log("ALARM", f"CAPTCHA WARNING DETECTED ({current_warning}/{max_warnings})!")
                await self.play_beep()
                self._show_desktop_notification(f"Captcha warning {current_warning}/{max_warnings} detected!")
                self._send_webhook("CAPTCHA WARNING", f"Warning {current_warning}/{max_warnings}\nMessage:\n{content}")
                return
        has_image = len(message.attachments) > 0
        image_captcha_hit = self._contains_keyword(text_to_check, self.image_captcha_keywords)
        if has_image and image_captcha_hit:
            self.bot.paused = True
            self.bot.throttle_until = time.time() + 3600
            self.bot.stats['captcha_status'] = 'pending'
            self.bot.stats['captcha_alert_count'] = 0
            self.bot.stats['last_captcha_msg'] = text_to_check[:200]
            self.bot.log("ALARM", "IMAGE CAPTCHA DETECTED! Warning triggered.")
            await self.play_beep()
            self._show_desktop_notification("Image captcha detected! Check DMs.")
            img_urls = "\n".join([att.url for att in message.attachments])
            self._start_continuous_captcha_alert("IMAGE CAPTCHA DETECTED", f"Message:\n{content}\n\nImages:\n{img_urls}")
            return
        captcha_keywords_hit = self._contains_keyword(text_to_check, self.captcha_keywords)
        captcha_url = self._get_captcha_url(message)
        
        if not captcha_url:
            url_match = re.search(r'https?://owobot\.com/captcha/\S+', text_to_check)
            if url_match:
                captcha_url = url_match.group(0)
        
        if captcha_url or captcha_keywords_hit:
            self.bot.paused = True
            self.bot.throttle_until = time.time() + 3600
            self.bot.stats['captcha_status'] = 'pending'
            self.bot.stats['captcha_alert_count'] = 0
            self.bot.stats['last_captcha_msg'] = text_to_check[:200]
            self.bot.log("ALARM", "CAPTCHA DETECTED!")
            await self.play_beep()
            self._show_desktop_notification("Captcha detected!")
            self.bot.log("SYS", "Starting priority DM/webhook captcha alert loop immediately.")
            self._start_continuous_captcha_alert("CAPTCHA DETECTED", f"Solve: {captcha_url or 'https://owobot.com/captcha'}")
            
            sec_cfg = self.bot.config.get("security", {})
            sol_cfg = sec_cfg.get("captcha_solver", {})
            
            autosolved = False
            auto_attempted = False
            fail_reason = None
            if sol_cfg.get("enabled", True) and sol_cfg.get("api_key"):
                auto_attempted = True
                self.bot.log("SYS", f"Attempting {self.bot.web_solver.provider} auto-solve...")
                autosolved, fail_reason = await self.bot.web_solver.auto_verify(max_total_seconds=480)
                if autosolved:
                    self.bot.log("SUCCESS", f"{self.bot.web_solver.provider} solved successfully!")
                    self._show_desktop_notification("Captcha solved successfully!")
                    self.bot.stats['captcha_active'] = False
                    self.bot.stats['captcha_status'] = 'resolved'
                elif self.bot.stats.get('captcha_status', 'pending') == 'pending':
                    self.bot.log("ERROR", f"{self.bot.web_solver.provider} auto-solve failed: {fail_reason}")
                    self._show_desktop_notification("Auto-solve failed! Solve manually.")
                    self.bot.stats['captcha_status'] = 'failed'

            if (
                auto_attempted
                and not autosolved
                and self.bot.stats.get('captcha_status', 'pending') == 'failed'
            ):
                self.bot.log("SYS", "Auto-solve failed; sending final fail notification.")
                solve_link = captcha_url or "https://owobot.com/captcha"
                alert_msg = f"Solve: {solve_link}"
                if fail_reason:
                    alert_msg += f"\n\n⚠️ Auto-solve error ({self.bot.web_solver.provider}): {fail_reason}"
                diag = self.bot.web_solver.get_last_diagnostic_summary()
                if diag:
                    alert_msg += f"\n\n🧾 Trace: {diag}"
                self.bot.stats['captcha_active'] = False
                await self._notify_captcha_failed("CAPTCHA DETECTED", alert_msg, fail_reason)
                if sys.platform == "win32" and sec_cfg.get("open_captcha_url_on_pc", False):
                    self.bot.log("SYS", "Opening Captcha in Browser with Auto-Login...")
                    asyncio.create_task(self.bot.web_solver.open_in_browser(captcha_url))

            return

async def setup(bot):
    await bot.add_cog(Security(bot))
