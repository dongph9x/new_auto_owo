"""
STANDALONE TEST — NOT wired into the bot. Run this manually on a machine with a
real display (your laptop/desktop, NOT the headless VPS) to answer one question:

    Can SeleniumBase's CDP mode actually solve the hCaptcha OwO shows, and can we
    read out a usable h-captcha-response token afterwards?

If this script prints a token, the approach is viable and worth building into a
real service. If it can't even get past the checkbox, or gets past it but there's
no token in the DOM, stop here — CDP mode isn't a fit for this captcha.

Setup:
    pip install seleniumbase
    seleniumbase install chromedriver

Usage:
    # Default: hCaptcha's own public demo widget — always available, no need to
    # wait for your account to actually get flagged. Answers "does CDP mode beat
    # hCaptcha's bot-detection at all". NOT the exact OwO sitekey/difficulty config
    # (hCaptcha sitekeys are domain-locked, so OwO's real sitekey only works on
    # owobot.com — this is the closest proxy available without a live flag).
    python experiments/test_cdp_hcaptcha.py

    # If/when you actually have a real pending captcha for an account, test the
    # real thing instead:
    python experiments/test_cdp_hcaptcha.py --url "https://owobot.com/captcha/<real-uuid>"

What it does:
    1. Opens a REAL (non-headless) Chrome via SeleniumBase's CDP mode.
    2. Navigates to the target URL.
    3. Pauses so YOU can manually log in with Discord if the page asks for it
       (this script does not touch your bot's account token at all).
    4. Once you're on the actual captcha page, press Enter in this terminal.
    5. Tries seleniumbase's captcha-solving helpers.
    6. Checks the DOM for a filled-in h-captcha-response value and prints it.
"""

import argparse
import sys
import time

try:
    from seleniumbase import SB
except ImportError:
    print("Missing dependency. Run: pip install seleniumbase && seleniumbase install chromedriver")
    sys.exit(1)

# hCaptcha's own public demo page — a real, always-on hCaptcha widget for testing
# solvers, unrelated to any specific site. Use --url to point at a real OwO
# captcha link once you actually have one pending on an account.
DEFAULT_URL = "https://accounts.hcaptcha.com/demo"

TOKEN_JS = """
() => {
    const el = document.querySelector('[name="h-captcha-response"]')
        || document.querySelector('textarea[name="h-captcha-response"]')
        || document.getElementById('h-captcha-response');
    if (el && el.value) return el.value;

    // hCaptcha sometimes exposes the token via its own JS API instead of the DOM field.
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--uc", action="store_true", default=True, help="use UC (undetected) mode")
    args = parser.parse_args()

    print(f"Opening (visible) browser at: {args.url}")
    print("This is a REAL browser window on YOUR screen — I can't see or interact with it.")
    print("If this is the OwO captcha URL, log in with Discord there when prompted.\n")

    with SB(uc=True, test=True) as sb:
        sb.activate_cdp_mode(args.url)
        sb.sleep(2)

        input(
            "\n>>> Get to the point where you can SEE the hCaptcha checkbox/widget "
            "rendered on the page (log in first if this is the real OwO URL).\n"
            ">>> Once you can see it, press Enter here to continue... "
        )

        print("\nAttempting sb.cdp.solve_captcha() ...")
        solved_ok = False
        try:
            sb.cdp.solve_captcha()
            solved_ok = True
            print("solve_captcha() returned without raising.")
        except Exception as e:
            print(f"solve_captcha() raised: {e}")

        print("\nAttempting sb.cdp.uc_gui_click_captcha() as a fallback ...")
        try:
            sb.cdp.uc_gui_click_captcha()
        except Exception as e:
            print(f"uc_gui_click_captcha() raised (may be expected if already solved): {e}")

        sb.sleep(2)

        print("\nChecking DOM for an h-captcha-response token ...")
        token = None
        try:
            token = sb.cdp.evaluate(TOKEN_JS)
        except Exception as e:
            print(f"Token extraction JS failed: {e}")

        print("\n" + "=" * 60)
        if token:
            print("RESULT: TOKEN FOUND")
            print(f"h-captcha-response = {token[:60]}... (len={len(token)})")
            print("\n=> CDP mode looks viable for this captcha. Worth building the real integration.")
        else:
            print("RESULT: NO TOKEN FOUND")
            print(f"(solve_captcha() completed without error: {solved_ok})")
            print(
                "\n=> Either the widget wasn't actually solved, or OwO's hCaptcha is the "
                "image-selection variant (not just checkbox), which CDP mode does not solve.\n"
                "   Check the browser window manually: does the checkbox show a green check?"
            )
        print("=" * 60)

        input("\nPress Enter to close the browser...")


if __name__ == "__main__":
    main()
