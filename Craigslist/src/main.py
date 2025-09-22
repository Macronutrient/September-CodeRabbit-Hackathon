"""Main entry point for Craigslist Post Helper."""

import asyncio
from browser_use import Browser
from .config import build_config
from .cookies import CookieManager
from .auth import AuthManager
from .images import ImageManager
from .agent import CraigslistAgent


async def main():
    """Main application entry point."""
    print("Starting Craigslist Post Helper...")
    
    # Build configuration from CLI args and environment
    try:
        cfg = build_config()
        cfg.log_config()
        
        # Validate API key early
        cfg.validate_api_key()
    except ValueError as e:
        print(f"[config] {e}")
        return
    
    # Initialize managers
    cookie_manager = CookieManager(cfg.email)
    auth_manager = AuthManager(cfg.email)
    image_manager = ImageManager(cfg.images)
    
    browser = None
    try:
        # Launch browser and initialize agent
        print("[startup] Launching browser and LLM client…")
        browser = Browser(keep_alive=True, wait_between_actions=0.1)
        await browser.start()
        
        # Install element highlight overlay (captures clicks/focus) if enabled
        if cfg.highlight:
            try:
                print("[ux] Installing highlight overlay for interacted elements…")
                cdp_session = await browser.get_or_create_cdp_session()  # type: ignore[attr-defined]
                highlight_script = r"""
                (function(){try{
                  if (window.__cl_highlight_installed) return;
                  window.__cl_highlight_installed = true;
                  const ov = document.createElement('div');
                  ov.id = '__cl_highlight_box';
                  Object.assign(ov.style, {
                    position: 'fixed',
                    border: '2px solid #00e5ff',
                    borderRadius: '4px',
                    background: 'rgba(0,229,255,0.08)',
                    pointerEvents: 'none',
                    zIndex: '2147483647',
                    display: 'none',
                    transition: 'all 0.05s ease'
                  });
                  document.documentElement.appendChild(ov);
                  const show = (el) => {
                    if (!el || !el.getBoundingClientRect) return;
                    const r = el.getBoundingClientRect();
                    ov.style.left = r.left + 'px';
                    ov.style.top = r.top + 'px';
                    ov.style.width = Math.max(0, r.width) + 'px';
                    ov.style.height = Math.max(0, r.height) + 'px';
                    ov.style.display = 'block';
                    clearTimeout(ov._t);
                    ov._t = setTimeout(() => { ov.style.display = 'none'; }, 1200);
                  };
                  window.__cl_highlight = show;
                  const onEv = (e) => { show(e.target); };
                  document.addEventListener('mousedown', onEv, {capture:true});
                  document.addEventListener('click', onEv, {capture:true});
                  document.addEventListener('focusin', onEv, {capture:true});
                  document.addEventListener('keyup', onEv, {capture:true});
                }catch(e){}})();
                """
                # Inject on every new document
                await cdp_session.cdp_client.send.Page.addScriptToEvaluateOnNewDocument(  # type: ignore[attr-defined]
                    params={"source": highlight_script},
                    session_id=cdp_session.session_id,
                )
                # Also install immediately on current document (if any)
                await cdp_session.cdp_client.send.Runtime.evaluate(  # type: ignore[attr-defined]
                    params={"expression": highlight_script, "returnByValue": True},
                    session_id=cdp_session.session_id,
                )
            except Exception as e:
                print(f"[ux] Highlight overlay install failed: {e}")
        
        # Navigate to SF Bay Craigslist homepage first (then login as needed)
        try:
            print("[nav] Opening Craigslist SF Bay Area homepage…")
            await browser._cdp_navigate("https://sfbay.craigslist.org/")  # type: ignore[attr-defined]
            cdp_session = await browser.get_or_create_cdp_session()  # type: ignore[attr-defined]
            for _ in range(20):
                result = await cdp_session.cdp_client.send.Runtime.evaluate(  # type: ignore[attr-defined]
                    params={"expression": "document.readyState", "returnByValue": True},
                    session_id=cdp_session.session_id,
                )
                state = (result or {}).get("result", {}).get("value", "")
                if state == "complete":
                    break
                await asyncio.sleep(0.25)
            print("[nav] Homepage loaded.")
        except Exception as e:
            print(f"[nav] Warning: could not load homepage: {e}")
        
        agent = CraigslistAgent(cfg, browser)
        
        # Load cookies and check login status
        cookies_loaded = await cookie_manager.load_session(browser)
        logged_in = False
        
        if cookies_loaded:
            logged_in = await auth_manager.check_login_status(browser)
            if logged_in:
                print("[cookies] Using saved session; skipping login.")
            else:
                print("[cookies] Saved cookies invalid/expired; proceeding with email login.")
        
        # Handle authentication workflow
        if logged_in:
            # Use existing session to navigate to posting form
            success = await agent.navigate_to_posting_form_with_cookies()
            if not success:
                print("[abort] Could not reach the posting form in time. Check network/site status and retry.")
                return
        else:
            # Perform email login flow
            success = await agent.initiate_email_login()
            if not success:
                print("[abort] Login flow didn't complete in time. Re-run and try again.")
                return
            
            # Get magic link from user
            magic_link = await auth_manager.get_magic_link_from_user()
            if not auth_manager.validate_magic_link(magic_link):
                return
            
            # Complete login with magic link
            success = await agent.complete_magic_link_login(magic_link)
            if not success:
                print("[abort] Failed to complete login and reach the posting form in time.")
                return
            
            # Verify login and save cookies
            logged_in = await auth_manager.check_login_status(browser)
            if not logged_in:
                print("[auth] Warning: Login verification failed after email flow. Proceeding to save cookies anyway for inspection.")
            else:
                print("[cookies] Login verified. Persisting cookies immediately…")
            await cookie_manager.save_session(browser)
        
        # Fill out the posting form
        success = await agent.fill_posting_form()
        if not success:
            print("[abort] Form filling phase exceeded time limit. Exiting to avoid indefinite hang.")
            await cookie_manager.save_session(browser)
            return
        
        # Handle image uploads
        image_manager.log_image_status()
        if image_manager.has_images():
            resolved_images = image_manager.resolve_images()
            success = await agent.upload_images(resolved_images)
            if not success:
                print("[warn] Image upload phase timed out. You can upload images manually in the open browser window.")
            await cookie_manager.save_session(browser)
        
        # Publish the post from the preview page
        success = await agent.publish_post()
        if not success:
            print("[warn] Publish phase did not complete in time. You can press the publish button manually in the open browser window.")
        await cookie_manager.save_session(browser)
        
        print("[success] Craigslist posting workflow completed successfully!")
        
    except Exception as e:
        print(f"[error] Unexpected error: {e}")
        if browser:
            await cookie_manager.save_session(browser)
    finally:
        if browser is not None:
            await cookie_manager.cleanup_session(browser)


if __name__ == "__main__":
    asyncio.run(main())
