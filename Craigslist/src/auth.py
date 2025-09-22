"""Authentication management for Craigslist login."""

import asyncio
import os
from typing import Tuple
from browser_use import Browser


async def is_logged_in(browser: Browser) -> bool:
    """Navigate to account area and robustly detect logged-in state.

    Heuristics:
    - Logged-in if we can see a "log out" action or the "make new post" link/button.
    - Not logged-in if we see the email login form and no logged-in markers.
    - Poll briefly to allow redirects from /login -> /home.
    """
    try:
        # Navigate to the login endpoint (Craigslist typically redirects to /home if already authenticated)
        await browser._cdp_navigate("https://accounts.craigslist.org/login")  # type: ignore[attr-defined]
        cdp_session = await browser.get_or_create_cdp_session()  # type: ignore[attr-defined]

        script = r"""
        (() => {
          const byText = (txt) => {
            const t = (txt || '').toLowerCase();
            return Array.from(document.querySelectorAll('a,button'))
              .some(el => ((el.textContent || '').toLowerCase().includes(t)));
          };
          const emailInput = document.querySelector('input#inputEmailHandle, input[name="inputEmailHandle"]');
          const loginForm = document.querySelector('form[action*="login" i], form[action*="signin" i]');
          const logoutByText = byText('log out');
          const logoutHref = !!document.querySelector('a[href*="logout" i]');
          const makeNewPost = byText('make new post');
          return {
            hasLoginForm: !!(emailInput || loginForm),
            hasLogout: !!(logoutByText || logoutHref),
            hasMakeNewPost: !!makeNewPost,
            href: location.href,
            ready: document.readyState
          };
        })()
        """

        last_href = ""
        # Poll for up to ~10 seconds (20 * 0.5s) to allow redirects and slow loads
        for _ in range(20):
            result = await cdp_session.cdp_client.send.Runtime.evaluate(  # type: ignore[attr-defined]
                params={"expression": script, "returnByValue": True},
                session_id=cdp_session.session_id,
            )
            val = (result or {}).get("result", {}).get("value", {}) or {}
            has_logout = bool(val.get("hasLogout"))
            has_mnp = bool(val.get("hasMakeNewPost"))
            has_login = bool(val.get("hasLoginForm"))
            href = val.get("href", "") or ""
            last_href = href or last_href

            # Definitive logged-in signals
            if has_logout or has_mnp:
                return True

            # If we clearly see the login form and no logged-in signals, likely not logged in
            # But give the first few iterations time to redirect away from /login
            if has_login and not (has_logout or has_mnp):
                # Keep polling for a few cycles if we're still on a /login URL that might redirect
                if "/login" in href and "accounts.craigslist.org" in href:
                    await asyncio.sleep(0.5)
                    continue
                return False

            # Indeterminate; wait a bit and try again
            await asyncio.sleep(0.5)

        # Fallback: if we ended up on an account home URL, assume logged-in
        if "accounts.craigslist.org" in last_href and "/home" in last_href:
            return True
        return False
    except Exception as e:
        print(f"[auth] Warning: could not verify login status: {e}")
        return False


class AuthManager:
    """Manages Craigslist authentication workflow."""
    
    def __init__(self, email: str):
        self.email = email
        
    async def check_login_status(self, browser: Browser) -> bool:
        """Check if user is currently logged in to Craigslist."""
        return await is_logged_in(browser)
        
    async def get_magic_link_from_user(self) -> str:
        """Get the magic link from the user.

        Supports two modes:
        - CLI mode: prompts on stdin as before.
        - Web/automation mode: if MAGIC_LINK_FILE is set in the environment, poll that file
          until a non-empty link appears, then return it.
        """
        file_path = os.getenv("MAGIC_LINK_FILE", "").strip()
        if file_path:
            print(f"[action] Waiting for magic link via file: {file_path}")
            print("[action] Frontend users can paste the link into the web form; the backend will detect it automatically.")
            # Poll up to ~10 minutes
            for _ in range(1200):  # 1200 * 0.5s = 600s (10 min)
                try:
                    if os.path.exists(file_path):
                        try:
                            with open(file_path, "r", encoding="utf-8") as f:
                                link = (f.read() or "").strip()
                                if link:
                                    print("[action] Magic link detected via file.")
                                    return link
                        except Exception:
                            pass
                except Exception:
                    pass
                await asyncio.sleep(0.5)
            print("[abort] Timed out waiting for magic link file content.")
            return ""
        # Fallback: CLI prompt
        print("[action] Check your email and copy the Craigslist login link (magic link).")
        link = await asyncio.to_thread(
            input,
            "Enter the link you received in your email (or press Enter to cancel): "
        )
        return link.strip()
        
    def validate_magic_link(self, link: str) -> bool:
        """Validate that the provided link looks like a valid magic link."""
        if not link:
            print("[abort] No link provided. Exiting so the script does not wait indefinitely.")
            return False
        return True
