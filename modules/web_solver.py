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
import aiohttp
import time
import json
import re
import subprocess

# capsolver/yescaptcha implement the same createTask/getTaskResult/getBalance contract
# (same request/response shape, same solution.gRecaptchaResponse field), so a single
# code path drives both — only the base URL, task type name, and the balance
# unit/threshold differ. nopecha uses a different wire format entirely (job-id based
# polling on the same /token/ endpoint) and is handled by its own branch below.
CAPTCHA_PROVIDERS = {
    "capsolver": {
        "base_url": "https://api.capsolver.com",
        "task_type": "HCaptchaTaskProxyLess",
        "min_balance": 0.002,  # CapSolver balance is denominated in USD
    },
    "yescaptcha": {
        "base_url": "https://api.yescaptcha.com",
        "task_type": "HCaptchaTaskProxyless",
        "min_balance": 30,  # YesCaptcha balance is denominated in its own points unit
    },
    "nopecha": {
        "base_url": "https://api.nopecha.com",
        "min_balance": 5,  # 1 hCaptcha solve costs 5 credits
    },
}

class WebSolver:
    def __init__(self, bot):
        self.bot = bot
        cfg = self.bot.config.get('security', {}).get('captcha_solver', {})
        self.api_key = cfg.get('api_key', '')
        self.enabled = cfg.get('enabled', True)
        self.provider = cfg.get('provider', 'nopecha')
        self.browser_cfg = cfg.get('browser_config', {})
        self.site_key = "a6a1d5ce-612d-472d-8e37-7601408fbc09"
        self.auth_url = "https://discord.com/api/v9/oauth2/authorize?client_id=408785106942164992&response_type=code&redirect_uri=https://owobot.com/api/auth/discord/redirect&scope=identify guilds"

    def _provider_cfg(self):
        return CAPTCHA_PROVIDERS.get(self.provider, CAPTCHA_PROVIDERS["nopecha"])

    async def get_balance(self):
        if not self.api_key: return 0
        prov = self._provider_cfg()
        try:
            async with aiohttp.ClientSession() as session:
                if self.provider == "nopecha":
                    url = f"{prov['base_url']}/status/"
                    async with session.get(url, params={"key": self.api_key}, timeout=10) as resp:
                        data = await resp.json()
                        return float(data.get("credit", 0))
                else:
                    url = f"{prov['base_url']}/getBalance"
                    async with session.post(url, json={"clientKey": self.api_key}, timeout=10) as resp:
                        data = await resp.json()
                        return float(data.get("balance", 0)) if data.get("errorId") == 0 else 0
        except: return 0

    async def solve_hcaptcha(self, retries=3):
        """solves hcaptcha using the configured provider's API and returns the token"""
        prov = self._provider_cfg()
        if self.provider == "nopecha":
            return await self._solve_hcaptcha_nopecha(prov, retries)

        create_url = f"{prov['base_url']}/createTask"
        result_url = f"{prov['base_url']}/getTaskResult"

        payload = {
            "clientKey": self.api_key,
            "task": {
                "type": prov["task_type"],
                "websiteKey": self.site_key,
                "websiteURL": "https://owobot.com",
            },
        }
        if self.provider == "yescaptcha":
            payload["softID"] = 94493

        async with aiohttp.ClientSession() as session:
            for attempt in range(retries):
                try:
                    self.bot.log("SYS", f"Creating {self.provider} task (Attempt {attempt+1})...")
                    async with session.post(create_url, json=payload) as resp:
                        data = await resp.json()

                    if data.get("errorId") != 0:
                        self.bot.log("ERROR", f"{self.provider} Error: {data.get('errorDescription')}")
                        continue

                    task_id = data.get("taskId")
                    for _ in range(60):
                        await asyncio.sleep(2)
                        async with session.post(result_url, json={"clientKey": self.api_key, "taskId": task_id}) as res_resp:
                            res = await res_resp.json()

                        if res.get("status") == "ready":
                            return res["solution"]["gRecaptchaResponse"]
                        if res.get("errorId") != 0: break
                except Exception as e:
                    self.bot.log("ERROR", f"Solver task failed: {e}")
            return None

    async def _solve_hcaptcha_nopecha(self, prov, retries=3):
        """nopecha's Token API: POST /token/ returns a job id in `data`, then GET
        /token/?id=<job_id> is polled until `data` holds the solved token (error 14
        means "still processing", any other error is a hard failure for that job)."""
        url = f"{prov['base_url']}/token/"
        payload = {
            "key": self.api_key,
            "type": "hcaptcha",
            "sitekey": self.site_key,
            "url": "https://owobot.com",
        }

        async with aiohttp.ClientSession() as session:
            for attempt in range(retries):
                try:
                    self.bot.log("SYS", f"Creating nopecha task (Attempt {attempt+1})...")
                    async with session.post(url, json=payload) as resp:
                        data = await resp.json()

                    job_id = data.get("data")
                    if not job_id:
                        self.bot.log("ERROR", f"nopecha Error: {data.get('message', data)}")
                        continue

                    for _ in range(60):
                        await asyncio.sleep(2)
                        async with session.get(url, params={"key": self.api_key, "id": job_id}) as res_resp:
                            res = await res_resp.json()

                        if res.get("data"):
                            return res["data"]
                        if res.get("error") is not None and res.get("error") != 14:
                            break  # anything other than "job incomplete" is a hard failure
                except Exception as e:
                    self.bot.log("ERROR", f"Solver task failed: {e}")
            return None

    async def auto_verify(self, tries=3):

        if not self.api_key:
            self.bot.log("ERROR", f"{self.provider} API key missing in settings.")
            return False

        balance = await self.get_balance()
        min_balance = self._provider_cfg()["min_balance"]
        if balance < min_balance:
            self.bot.log("ERROR", f"{self.provider} balance too low: {balance}")
            return False

        headers = {
            "Authorization": self.bot.token,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x44) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                auth_payload = {
                    "authorize": True,
                    "permissions": "0",
                    "integration_type": 0,
                    "location_context": {"guild_id": "10000", "channel_id": "10000", "channel_type": 10000}
                }
                async with session.post(self.auth_url, json=auth_payload) as resp:
                    if resp.status != 200: return False
                    auth_data = await resp.json()
                    redirect_url = auth_data.get("location")

                if redirect_url:
                    async with session.get(redirect_url) as r: pass


                solution = await self.solve_hcaptcha(tries)
                if not solution: return False

                verify_url = "https://owobot.com/api/captcha/verify"
                verify_payload = {"token": solution}
                async with session.post(verify_url, json=verify_payload, headers={"Referer": "https://owobot.com/captcha", "Origin": "https://owobot.com"}) as v_resp:
                    return v_resp.status == 200
            except Exception as e:
                self.bot.log("ERROR", f"Auto-verification failed: {e}")
                return False

    async def open_in_browser(self, captcha_url=None):
        """gets oauth redirect url and opens it in browser for auto-login/manual solve"""
        headers = {
            "Authorization": self.bot.token,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            try:
                auth_payload = {
                    "authorize": True,
                    "permissions": "0",
                    "integration_type": 0,
                    "location_context": {"guild_id": "10000", "channel_id": "10000", "channel_type": 10000}
                }
                
                auth_url = self.auth_url
                if captcha_url:
                    from urllib.parse import quote
                    auth_url += f"&state={quote(captcha_url)}"

                async with session.post(auth_url, json=auth_payload) as resp:
                    if resp.status != 200:
                        self.bot.log("ERROR", f"Browser Solver: OAuth failed (Status {resp.status})")
                        if captcha_url:
                            self.bot.log("SYS", "OAuth failed. Opening raw captcha URL as fallback.")
                            subprocess.Popen(f'start "" "{captcha_url}"', shell=True)
                        return False
                    
                    auth_data = await resp.json()
                    redirect_url = auth_data.get("location")

                if redirect_url:
                    self.bot.log("SYS", f"Opening Auth Login for {self.bot.username}...")
                    
                    try:
                        # chrome_path = self.browser_cfg.get('executable_path')
                        # user_data = self.browser_cfg.get('user_data_dir')
                        # profile = self.browser_cfg.get('profile_name', 'Default')
                        # if chrome_path and user_data:
                        #     subprocess.Popen([
                        #         chrome_path,
                        #         f'--user-data-dir={user_data}',
                        #         f'--profile-directory={profile}',
                        #         redirect_url
                        #     ])
                        # else:
                        subprocess.Popen(f'start "" "{redirect_url}"', shell=True)
                        
                        return True
                    except Exception as e:
                        self.bot.log("ERROR", f"Browser launch failed: {e}")
                        return False
                return False
            except Exception as e:
                self.bot.log("ERROR", f"Browser solver start failed: {e}")
                return False

def setup_web_solver(bot):
    return WebSolver(bot)
