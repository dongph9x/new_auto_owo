# CDP-based hCaptcha solver — a fallback captcha-solving path that doesn't depend
# on a paid third-party API (NopeCha/CapSolver). Runs in its own container because
# it needs a real Chrome + virtual display (Xvfb), unlike the rest of the bot.
#
# Flow for one solve request:
#   1. Do the SAME Discord OAuth handshake the main bot already uses (web_solver.py
#      auto_verify()) with `requests` instead of `aiohttp`, to get an authenticated
#      owobot.com session (cookies) for the given account token.
#   2. Launch a SeleniumBase CDP browser, inject those cookies so it opens already
#      logged in — no interactive/manual login, ever.
#   3. Navigate to the captcha page, try SeleniumBase's captcha-solving helpers.
#   4. Read the resulting h-captcha-response token out of the page.
#   5. Return it — the caller (web_solver.py) submits it to owobot's normal
#      /api/captcha/verify endpoint, exactly like the API-based providers do.
#
# NOTE: unverified in production — this is the "code it, test on the real
# environment" build. The cookie round-trip (requests.Session -> CDP cookie
# format) is the single highest-risk step; errors there are logged verbatim
# rather than swallowed, so a first real run tells us immediately if the cookie
# shape needs adjusting.

import asyncio
import logging
import os
import time

import requests
from flask import Flask, request, jsonify

logging.basicConfig(level=logging.INFO, format="[cdp-solver] %(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("cdp-solver")

app = Flask(__name__)

AUTH_URL = (
    "https://discord.com/api/v9/oauth2/authorize"
    "?client_id=408785106942164992&response_type=code"
    "&redirect_uri=https://owobot.com/api/auth/discord/redirect&scope=identify guilds"
)
CAPTCHA_BASE_URL = "https://owobot.com/captcha"
VERIFY_URL = "https://owobot.com/api/captcha/verify"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
CAPTCHA_RECOVERY_ROUNDS = 3
TOKEN_EXTRACTION_ATTEMPTS = 3
TOKEN_EXTRACTION_DELAY_SECONDS = 2

TOKEN_JS = """
() => {
    const el = document.querySelector('[name="h-captcha-response"]')
        || document.querySelector('textarea[name="h-captcha-response"]')
        || document.getElementById('h-captcha-response');
    if (el && el.value) return el.value;
    try {
        if (window.hcaptcha && typeof window.hcaptcha.getResponse === 'function') {
            const iframes = document.querySelectorAll('iframe[data-hcaptcha-widget-id]');
            for (const f of iframes) {
                const id = f.getAttribute('data-hcaptcha-widget-id');
                const resp = window.hcaptcha.getResponse(id);
                if (resp) return resp;
            }
            const resp = window.hcaptcha.getResponse();
            if (resp) return resp;
        }
    } catch (e) {}
    return null;
}
"""

RESET_JS = """
() => {
    try {
        if (window.hcaptcha && typeof window.hcaptcha.reset === 'function') {
            const iframes = document.querySelectorAll('iframe[data-hcaptcha-widget-id]');
            let didReset = false;
            for (const f of iframes) {
                const id = f.getAttribute('data-hcaptcha-widget-id');
                try {
                    window.hcaptcha.reset(id);
                    didReset = true;
                } catch (e) {}
            }
            if (!didReset) {
                window.hcaptcha.reset();
                didReset = true;
            }
            return didReset;
        }
    } catch (e) {}
    return false;
}
"""


def get_owobot_session_cookies(discord_token: str):
    """Same OAuth handshake as web_solver.py's auto_verify(), done synchronously
    with `requests` (this service is sync/Flask, unlike the main bot). Returns a
    list of CDP-shaped cookie dicts for owobot.com, or raises on failure."""
    headers = {
        "Authorization": discord_token,
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
    }
    session = requests.Session()
    session.headers.update(headers)

    auth_payload = {
        "authorize": True,
        "permissions": "0",
        "integration_type": 0,
        "location_context": {"guild_id": "10000", "channel_id": "10000", "channel_type": 10000},
    }
    resp = session.post(AUTH_URL, json=auth_payload, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"Discord OAuth authorize failed (HTTP {resp.status_code}): {resp.text[:300]}")
    redirect_url = resp.json().get("location")
    if not redirect_url:
        raise RuntimeError("OAuth authorize response had no redirect location")

    # Following this sets the owobot.com session cookie in `session`.
    session.get(redirect_url, timeout=15)

    cdp_cookies = []
    for c in session.cookies:
        cdp_cookies.append({
            "name": c.name,
            "value": c.value,
            "domain": c.domain or "owobot.com",
            "path": c.path or "/",
            "secure": bool(c.secure),
            "httpOnly": bool(getattr(c, "_rest", {}).get("HttpOnly", False)),
        })
    if not cdp_cookies:
        raise RuntimeError("OAuth succeeded but no cookies were captured — can't authenticate the browser")
    return cdp_cookies


async def _read_token_with_retries(page, round_idx):
    for token_attempt in range(1, TOKEN_EXTRACTION_ATTEMPTS + 1):
        try:
            token = await page.evaluate(TOKEN_JS)
            if token:
                log.info(f"Round {round_idx}: token extracted on read attempt {token_attempt}.")
                return token
        except Exception as e:
            log.error(f"Round {round_idx}: token extraction JS failed (attempt {token_attempt}): {e}")
        await asyncio.sleep(TOKEN_EXTRACTION_DELAY_SECONDS)
    return None


async def _solve_async(captcha_url: str, cdp_cookies: list):
    from seleniumbase import cdp_driver

    # Xvfb is already managed by container entrypoint; avoid starting a second
    # nested Xvfb here (can cause display lock/race issues).
    driver = await cdp_driver.start_async(headless=False, xvfb=False)
    try:
        # Must land on the target origin once before cookies for that domain apply.
        await driver.get("https://owobot.com")
        await driver.cookies.set_all(cdp_cookies)
        page = await driver.get(captcha_url)
        await asyncio.sleep(3)

        solved_any_round = False
        last_failed_stage = "init"

        for round_idx in range(1, CAPTCHA_RECOVERY_ROUNDS + 1):
            log.info(f"Solve round {round_idx}/{CAPTCHA_RECOVERY_ROUNDS} started.")
            try:
                await page.solve_captcha()
                solved_any_round = True
            except Exception as e:
                log.warning(f"Round {round_idx}: page.solve_captcha() raised: {e}")

            try:
                await page.uc_gui_click_captcha()
            except Exception as e:
                log.info(f"Round {round_idx}: uc_gui_click_captcha() raised (may be fine): {e}")

            await asyncio.sleep(2)
            token = await _read_token_with_retries(page, round_idx)
            if token:
                return token, solved_any_round, round_idx, None

            last_failed_stage = f"round_{round_idx}_token_missing"
            if round_idx >= CAPTCHA_RECOVERY_ROUNDS:
                break

            # Hard-captcha recovery: force reset the challenge, then reload page so
            # hCaptcha can issue a fresh puzzle before retrying.
            try:
                reset_ok = await page.evaluate(RESET_JS)
                log.info(f"Round {round_idx}: hcaptcha.reset() result={reset_ok}")
            except Exception as e:
                log.warning(f"Round {round_idx}: hcaptcha.reset() failed: {e}")
            try:
                page = await driver.get(captcha_url)
                await asyncio.sleep(2)
            except Exception as e:
                last_failed_stage = f"round_{round_idx}_reload_failed"
                log.warning(f"Round {round_idx}: captcha page reload failed: {e}")

        return None, solved_any_round, CAPTCHA_RECOVERY_ROUNDS, last_failed_stage
    finally:
        driver.stop()


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/solve", methods=["POST"])
def solve():
    data = request.get_json(force=True, silent=True) or {}
    discord_token = data.get("discord_token")
    uuid = data.get("uuid")
    captcha_url = data.get("captcha_url") or (f"{CAPTCHA_BASE_URL}/{uuid}" if uuid else CAPTCHA_BASE_URL)

    if not discord_token:
        return jsonify({"success": False, "error": "discord_token is required"}), 400

    masked_token = (
        f"{discord_token[:6]}...{discord_token[-4:]}"
        if isinstance(discord_token, str) and len(discord_token) >= 12
        else "short/invalid"
    )
    log.info(f"/solve request received (captcha_url={captcha_url}, token={masked_token})")

    start = time.time()
    try:
        cdp_cookies = get_owobot_session_cookies(discord_token)
    except Exception as e:
        log.exception(f"Cookie handshake failed: {e}")
        return jsonify({"success": False, "error": f"auth failed: {e}"}), 200

    try:
        token, solved, rounds_attempted, failed_stage = asyncio.run(_solve_async(captcha_url, cdp_cookies))
    except Exception as e:
        log.exception(f"CDP solve failed: {e}")
        return jsonify({"success": False, "error": f"solve failed: {e}"}), 200

    elapsed = round(time.time() - start, 1)
    if token:
        log.info(f"Solved in {elapsed}s.")
        return jsonify({"success": True, "token": token, "elapsed": elapsed})

    error_msg = (
        "no h-captcha-response token found after solve attempt "
        f"(rounds={rounds_attempted}, failed_stage={failed_stage})"
    )
    log.warning(
        f"No token after {elapsed}s (solve_captcha() completed_any_round={solved}, "
        f"rounds={rounds_attempted}, failed_stage={failed_stage})."
    )
    return jsonify({
        "success": False,
        "error": error_msg,
        "solve_captcha_completed": solved,
        "rounds_attempted": rounds_attempted,
        "failed_stage": failed_stage,
        "elapsed": elapsed,
    })


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8100))
    app.run(host="0.0.0.0", port=port)
