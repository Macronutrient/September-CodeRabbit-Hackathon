"""Cookie management for maintaining Craigslist sessions."""

import json
from pathlib import Path
from typing import Optional
from browser_use import Browser


COOKIES_DIR = Path(__file__).parent.parent / "cookies"


def cookie_file_for_email(email: str) -> Path:
    """Return a filesystem-safe cookie path for a given email."""
    safe = ''.join(ch if ch.isalnum() or ch in ('-', '_', '.') else '_' for ch in email.strip())
    return COOKIES_DIR / f"{safe}.json"


async def save_cookies(browser: Browser, path: Path) -> None:
    """Persist all cookies from the current context to disk as JSON."""
    try:
        cookies = []
        try:
            cookies = await browser._cdp_get_cookies()  # type: ignore[attr-defined]
        except Exception as e:
            print(f"[cookies] Primary cookie fetch failed (_cdp_get_cookies): {e}. Trying CDP fallback…")

        if not cookies:
            try:
                cdp_session = await browser.get_or_create_cdp_session()  # type: ignore[attr-defined]
                try:
                    await cdp_session.cdp_client.send.Network.enable(  # type: ignore[attr-defined]
                        params={},
                        session_id=cdp_session.session_id,
                    )
                except Exception as e:
                    print(f"[cookies] CDP Network.enable failed or unnecessary: {e}")

                res = await cdp_session.cdp_client.send.Network.getAllCookies(  # type: ignore[attr-defined]
                    session_id=cdp_session.session_id
                )
                cookies = (res or {}).get("cookies", [])
            except Exception as e:
                print(f"[cookies] CDP fallback failed (Network.getAllCookies): {e}")

        if not cookies:
            print("[cookies] No cookies found to save (empty set).")
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=2)
            print(f"[cookies] Wrote empty cookie jar to {path}")
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(cookies, f, ensure_ascii=False, indent=2)
        print(f"[cookies] Saved {len(cookies)} cookies to {path}")
    except Exception as e:
        print(f"[cookies] Warning: failed to save cookies: {e}")


async def load_cookies(browser: Browser, path: Path) -> bool:
    """Load cookies from disk into the current context; return True if loaded."""
    if not path.exists():
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
        await browser._cdp_set_cookies(cookies)  # type: ignore[attr-defined]
        print(f"[cookies] Loaded {len(cookies)} cookies from {path}")
        return True
    except Exception as e:
        print(f"[cookies] Warning: failed to load cookies: {e}")
        return False


class CookieManager:
    """Manages cookie persistence for browser sessions."""
    
    def __init__(self, email: str):
        self.email = email
        self.cookie_file = cookie_file_for_email(email)
        
    async def load_session(self, browser: Browser) -> bool:
        """Load existing session cookies for the browser."""
        print(f"[config] Using cookie file: {self.cookie_file}")
        return await load_cookies(browser, self.cookie_file)
        
    async def save_session(self, browser: Browser) -> None:
        """Save current browser session cookies."""
        await save_cookies(browser, self.cookie_file)
        
    async def cleanup_session(self, browser: Browser) -> None:
        """Final save of cookies before shutdown."""
        try:
            print("[cookies] Final save of cookies before shutdown…")
            await self.save_session(browser)
        except Exception as e:
            print(f"[cookies] Final save failed: {e}")
