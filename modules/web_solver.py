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
    # Fallback if not set in this account's config.
    DEFAULT_MAX_RETRY_SECONDS = 300

    def __init__(self, bot):
        self.bot = bot
        cfg = self.bot.config.get('security', {}).get('captcha_solver', {})
        self.api_key = cfg.get('api_key', '')
        self.enabled = cfg.get('enabled', True)
        self.provider = cfg.get('provider', 'nopecha')
        # Hard ceiling on total retry+poll time across ALL attempts combined, so a
        # slow/stuck solver can't eat into the window still needed for manual
        # solving. Per-account: some accounts may have more/less manual-response
        # time available, or need more patience for a provider's own internal
        # queue/retry cycle before giving up.
        self.max_retry_seconds = cfg.get('max_retry_seconds', self.DEFAULT_MAX_RETRY_SECONDS)
        self.browser_cfg = cfg.get('browser_config', {})
        self.site_key = "a6a1d5ce-612d-472d-8e37-7601408fbc09"
        self.auth_url = "https://discord.com/api/v9/oauth2/authorize?client_id=408785106942164992&response_type=code&redirect_uri=https://owobot.com/api/auth/discord/redirect&scope=identify guilds"
        # Free fallback: a real Chrome (CDP mode) solving the captcha locally instead
        # of a paid API. Internal-only service, see cdp_solver/. Unproven in
        # production yet — set provider to "cdp_local" to try it.
        self.cdp_solver_url = cfg.get('cdp_solver_url', 'http://cdp-solver:8100').rstrip('/')
        # Optional secondary provider, tried only if the primary one fails (e.g.
        # nopecha is overloaded/timing out) — before giving up and falling back to
        # the DM/webhook manual-solve alert. Leave provider_2nd unset/empty to
        # disable (single-provider behaviour, unchanged from before).
        self.provider_2nd = cfg.get('provider_2nd') or None
        self.api_key_2nd = cfg.get('api_key_2nd', '')
        self.max_retry_seconds_2nd = cfg.get('max_retry_seconds_2nd', self.max_retry_seconds)

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

    async def solve_hcaptcha(self, retries=3, deadline=None):
        """Solves hcaptcha using the configured provider's API.
        `deadline` (a time.time()-based timestamp) caps the TOTAL time spent across
        ALL attempts + polling combined — defaults to self.max_retry_seconds from
        now if not given, so a slow/stuck solver can't run past that budget.
        Returns (token_or_None, last_error_reason) — reason is None on success."""
        if deadline is None:
            deadline = time.time() + self.max_retry_seconds

        prov = self._provider_cfg()
        if self.provider == "nopecha":
            return await self._solve_hcaptcha_nopecha(prov, retries, deadline)

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

        last_error = "unknown error"
        async with aiohttp.ClientSession() as session:
            for attempt in range(retries):
                if time.time() >= deadline:
                    last_error = f"gave up: exceeded the {self.max_retry_seconds}s retry budget"
                    self.bot.log("WARN", f"{self.provider}: {last_error}")
                    break
                try:
                    self.bot.log("SYS", f"Creating {self.provider} task (Attempt {attempt+1}/{retries})...")
                    async with session.post(create_url, json=payload) as resp:
                        if resp.status != 200:
                            last_error = f"createTask returned HTTP {resp.status}"
                            self.bot.log("ERROR", f"{self.provider}: {last_error}")
                            continue
                        data = await resp.json()

                    if data.get("errorId") != 0:
                        last_error = f"createTask error: {data.get('errorDescription') or data.get('errorId')}"
                        self.bot.log("ERROR", f"{self.provider}: {last_error}")
                        continue

                    task_id = data.get("taskId")
                    poll_outcome = "timeout"
                    while time.time() < deadline:
                        await asyncio.sleep(2)
                        async with session.post(result_url, json={"clientKey": self.api_key, "taskId": task_id}) as res_resp:
                            res = await res_resp.json()

                        if res.get("status") == "ready":
                            return res["solution"]["gRecaptchaResponse"], None
                        if res.get("errorId") != 0:
                            last_error = f"getTaskResult error: {res.get('errorDescription') or res.get('errorId')}"
                            self.bot.log("ERROR", f"{self.provider}: {last_error}")
                            poll_outcome = "error"
                            break
                    if poll_outcome == "timeout":
                        last_error = f"gave up: exceeded the {self.max_retry_seconds}s retry budget while polling"
                        self.bot.log("WARN", f"{self.provider}: {last_error}")
                        break
                except Exception as e:
                    last_error = str(e)
                    self.bot.log("ERROR", f"{self.provider}: solver task failed: {last_error}")
            return None, last_error

    async def _solve_hcaptcha_nopecha(self, prov, retries=3, deadline=None):
        """nopecha's Token API: POST /token/ returns a job id in `data`, then GET
        /token/?id=<job_id> is polled until `data` holds the solved token (error 14
        means "still processing", any other error is a hard failure for that job).
        `deadline` caps total time across all attempts (see solve_hcaptcha).
        Returns (token_or_None, last_error_reason)."""
        if deadline is None:
            deadline = time.time() + self.max_retry_seconds

        url = f"{prov['base_url']}/token/"
        payload = {
            "key": self.api_key,
            "type": "hcaptcha",
            "sitekey": self.site_key,
            "url": "https://owobot.com",
        }

        last_error = "unknown error"
        async with aiohttp.ClientSession() as session:
            for attempt in range(retries):
                if time.time() >= deadline:
                    last_error = f"gave up: exceeded the {self.max_retry_seconds}s retry budget"
                    self.bot.log("WARN", f"nopecha: {last_error}")
                    break
                try:
                    self.bot.log("SYS", f"Creating nopecha task (Attempt {attempt+1}/{retries})...")
                    async with session.post(url, json=payload) as resp:
                        if resp.status != 200:
                            last_error = f"token/ create returned HTTP {resp.status}"
                            self.bot.log("ERROR", f"nopecha: {last_error}")
                            continue
                        data = await resp.json()

                    job_id = data.get("data")
                    if not job_id:
                        last_error = f"task rejected: {data.get('message') or data.get('error') or data}"
                        self.bot.log("ERROR", f"nopecha: {last_error}")
                        continue

                    poll_outcome = "timeout"
                    while time.time() < deadline:
                        await asyncio.sleep(2)
                        async with session.get(url, params={"key": self.api_key, "id": job_id}) as res_resp:
                            res = await res_resp.json()

                        if res.get("data"):
                            return res["data"], None
                        if res.get("error") is not None and res.get("error") != 14:
                            last_error = f"job failed: error {res.get('error')} - {res.get('message', '')}".strip(" -")
                            self.bot.log("ERROR", f"nopecha: {last_error}")
                            poll_outcome = "error"
                            break
                    if poll_outcome == "timeout":
                        last_error = f"gave up: exceeded the {self.max_retry_seconds}s retry budget while polling"
                        self.bot.log("WARN", f"nopecha: {last_error}")
                        break
                except Exception as e:
                    last_error = str(e)
                    self.bot.log("ERROR", f"nopecha: solver task failed: {last_error}")
            return None, last_error

    async def auto_verify(self, tries=3):
        """Tries the primary provider; if it fails and provider_2nd is configured,
        automatically tries the secondary provider before giving up. Returns
        (success: bool, reason: str|None) — reason is always populated on failure."""
        ok, reason = await self._auto_verify_single(tries)
        if ok or not self.provider_2nd:
            return ok, reason

        self.bot.log(
            "SYS",
            f"{self.provider}: primary provider failed ({reason}). "
            f"Trying secondary provider {self.provider_2nd}..."
        )

        # Swap in the secondary provider's settings for one attempt, then restore —
        # this bot processes one captcha at a time per account, so there's no
        # concurrent auto_verify() call that this swap could interfere with.
        orig = (self.provider, self.api_key, self.max_retry_seconds)
        try:
            self.provider = self.provider_2nd
            self.api_key = self.api_key_2nd
            self.max_retry_seconds = self.max_retry_seconds_2nd
            ok2, reason2 = await self._auto_verify_single(tries)
        finally:
            self.provider, self.api_key, self.max_retry_seconds = orig

        if ok2:
            return True, None
        return False, f"primary({orig[0]}): {reason}; secondary({self.provider_2nd}): {reason2}"

    async def _auto_verify_single(self, tries=3):
        """One provider attempt, using whatever self.provider/self.api_key currently
        are — see auto_verify() for the primary/secondary orchestration around this."""
        if self.provider == "cdp_local":
            return await self._auto_verify_cdp_local()

        if not self.api_key:
            reason = "API key missing in settings"
            self.bot.log("ERROR", f"{self.provider}: {reason}.")
            return False, reason

        balance = await self.get_balance()
        min_balance = self._provider_cfg()["min_balance"]
        if balance < min_balance:
            reason = f"balance too low ({balance} < {min_balance} required)"
            self.bot.log("ERROR", f"{self.provider}: {reason}")
            return False, reason

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
                    if resp.status != 200:
                        reason = f"Discord OAuth authorize failed (HTTP {resp.status})"
                        self.bot.log("ERROR", f"{self.provider}: {reason}")
                        return False, reason
                    auth_data = await resp.json()
                    redirect_url = auth_data.get("location")

                if redirect_url:
                    async with session.get(redirect_url) as r: pass

                solution, solve_reason = await self.solve_hcaptcha(tries)
                if not solution:
                    reason = f"failed to solve after {tries} attempt(s): {solve_reason}"
                    return False, reason

                verify_url = "https://owobot.com/api/captcha/verify"
                verify_payload = {"token": solution}
                async with session.post(verify_url, json=verify_payload, headers={"Referer": "https://owobot.com/captcha", "Origin": "https://owobot.com"}) as v_resp:
                    if v_resp.status == 200:
                        return True, None
                    reason = f"owobot verify endpoint returned HTTP {v_resp.status}"
                    self.bot.log("ERROR", f"{self.provider}: {reason}")
                    return False, reason
            except Exception as e:
                reason = str(e)
                self.bot.log("ERROR", f"{self.provider}: auto-verification failed: {reason}")
                return False, reason

    async def _auto_verify_cdp_local(self):
        """Free fallback path: ask the cdp-solver service (real Chrome, CDP mode,
        no paid API) to solve the captcha, then submit the resulting token to
        owobot exactly like the API-based providers do."""
        self.bot.log("SYS", f"cdp_local: requesting solve from {self.cdp_solver_url} ...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.cdp_solver_url}/solve",
                    json={"discord_token": self.bot.token},
                    timeout=aiohttp.ClientTimeout(total=self.max_retry_seconds + 30),
                ) as resp:
                    if resp.status != 200:
                        reason = f"cdp-solver service returned HTTP {resp.status}"
                        self.bot.log("ERROR", f"cdp_local: {reason}")
                        return False, reason
                    data = await resp.json()
        except Exception as e:
            reason = f"could not reach cdp-solver service: {e}"
            self.bot.log("ERROR", f"cdp_local: {reason}")
            return False, reason

        if not data.get("success") or not data.get("token"):
            reason = data.get("error") or "cdp-solver did not return a token"
            self.bot.log("ERROR", f"cdp_local: {reason}")
            return False, reason

        solution = data["token"]
        headers = {
            "Authorization": self.bot.token,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x44) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        verify_url = "https://owobot.com/api/captcha/verify"
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.post(
                    verify_url,
                    json={"token": solution},
                    headers={"Referer": "https://owobot.com/captcha", "Origin": "https://owobot.com"},
                ) as v_resp:
                    if v_resp.status == 200:
                        return True, None
                    reason = f"owobot verify endpoint returned HTTP {v_resp.status}"
                    self.bot.log("ERROR", f"cdp_local: {reason}")
                    return False, reason
        except Exception as e:
            reason = f"verify request failed: {e}"
            self.bot.log("ERROR", f"cdp_local: {reason}")
            return False, reason

    async def fetch_battle_log(self, uuid):
        """Pull the structured battle-log replay JSON for `uuid` — the same data the
        website's battle-log page renders. Endpoint reverse-engineered from owobot.com's
        JS bundle (`getBattleLog`): the replay lives on a public logs server at
        `https://logs.owobot.com/logs/<uuid>` and needs no auth (the site fetches it
        without credentials). The `/api/battle-log` endpoint we used before is actually
        the *saved-logs list* (`?page=&limit=`), which ignores a uuid and returns [].
        Returns the parsed JSON dict, or None on failure."""
        url = f"https://logs.owobot.com/logs/{uuid}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": f"https://owobot.com/battle-log?uuid={uuid}",
        }
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url) as r:
                    if r.status != 200:
                        self.bot.log("WARN", f"BattleLog: logs server returned HTTP {r.status} for {uuid}")
                        return None
                    data = await r.json()
                    if not data:
                        self.bot.log("WARN", f"BattleLog: logs server returned empty for {uuid}")
                        return None
                    return data
        except Exception as e:
            self.bot.log("ERROR", f"BattleLog: fetch failed: {e}")
            return None

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
