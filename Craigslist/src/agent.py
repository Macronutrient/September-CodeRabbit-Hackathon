"""Agent workflow management for Craigslist posting automation."""

import asyncio
from typing import Tuple, Optional, Any
from browser_use import Agent, Browser, ChatGoogle
try:
    from browser_use import ChatOpenAI
except ImportError:
    # If ChatOpenAI is not available in this browser-use version, we handle it later in __init__
    ChatOpenAI = None

from .config import Config


async def run_with_timeout(coro, timeout: float, phase: str) -> Tuple[bool, Optional[Any]]:
    """Run an awaitable with a timeout, logging start/finish. Returns (ok, result)."""
    print(f"[phase] Starting: {phase} (timeout={int(timeout)}s)")
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        print(f"[phase] Completed: {phase}")
        return True, result
    except asyncio.TimeoutError:
        print(f"[timeout] Phase timed out: {phase} after {int(timeout)}s")
        return False, None
    except Exception as e:
        print(f"[error] Phase failed: {phase}: {e}")
        return False, None


async def agent_run(agent: Agent, max_steps: int, timeout: int, phase: str) -> Tuple[bool, Optional[Any]]:
    """Wrapper to run Agent.run with unified timeout handling and error capture."""
    try:
        return await run_with_timeout(agent.run(max_steps=max_steps), timeout=timeout, phase=phase)
    except Exception as e:
        print(f"[agent] Error during phase '{phase}': {e}")
        return False, None


class CraigslistAgent:
    """Manages the browser-use agent workflow for Craigslist posting."""
    
    def __init__(self, config: Config, browser: Browser):
        self.config = config
        self.browser = browser
        
        # Initialize LLM strictly per ENV-configured provider/model (no in-code defaults)
        api_key, provider = config.validate_api_key()
        model = (self.config.llm_model or "").strip()
        if provider == "openai":
            if not ChatOpenAI:
                raise ValueError("[llm] LLM_PROVIDER=openai but ChatOpenAI is unavailable in browser-use. Install a version exposing ChatOpenAI or set LLM_PROVIDER=google.")
            print(f"[llm] Using OpenAI {model} (key: ...{api_key[-8:]})")
            self.llm = ChatOpenAI(model=model, api_key=api_key)
        elif provider == "google":
            print(f"[llm] Using Google Gemini {model} (key: ...{api_key[-8:]})")
            self.llm = ChatGoogle(model=model)
        else:
            raise ValueError(f"[llm] Unsupported provider '{provider}' from config")
        
        self.agent: Optional[Agent] = None
        
    def create_agent(self, task: str, available_file_paths: Optional[list[str]] = None) -> Agent:
        """Create a new agent with the specified task."""
        kwargs = {
            "task": task,
            "llm": self.llm,
            "headless": self.config.headless,
            "browser_session": self.browser,
        }
        if available_file_paths:
            kwargs["available_file_paths"] = available_file_paths
        self.agent = Agent(**kwargs)
        return self.agent
        
    async def navigate_to_posting_form_with_cookies(self) -> bool:
        """Navigate directly to posting form using saved cookies."""
        task = (
            f"Navigate to https://post.craigslist.org and press the create a post button, "
            f"click for sale by owner, {self.config.category} continue until you reach the form to fill out the posting details"
            f"if the page asks for 'choose the location that fits best:', select the first option."
        )
        agent = self.create_agent(task)
        ok, _ = await agent_run(
            agent, 
            max_steps=40, 
            timeout=self.config.t_long, 
            phase="Navigate to posting form (using cookies)"
        )
        return ok
        
    async def initiate_email_login(self) -> bool:
        """Start the email login flow."""
        task = (
            "First go to https://sfbay.craigslist.org/ and wait for the homepage to fully load. "
            "Then go to the login page by either clicking the 'my account' or 'log in' link, or by navigating directly to https://accounts.craigslist.org/login. "
            f"On the login page, set the email to {self.config.email} and press the 'email login link' button."
        )
        agent = self.create_agent(task)
        ok, _ = await agent_run(
            agent, 
            max_steps=16, 
            timeout=self.config.t_long, 
            phase="Initiate email login link flow"
        )
        return ok
        
    async def complete_magic_link_login(self, magic_link: str) -> bool:
        """Complete login using magic link and navigate to posting form."""
        if not self.agent:
            raise ValueError("Agent not initialized. Call initiate_email_login first.")
            
        self.agent.add_new_task(
            f"Navigate to {magic_link} and press the create a post button, click for sale by owner, {self.config.category} "
            f"if you are on a page that asks for location, put the city from: '{self.config.address}'. "
            f"continue until you reach the form to fill out the posting details"
            f"if the page asks for 'choose the location that fits best:', select the first option."
        )
        ok, _ = await agent_run(
            self.agent, 
            max_steps=40, 
            timeout=self.config.t_long, 
            phase="Open magic link and reach posting form"
        )
        return ok
        
    async def fill_posting_form(self) -> bool:
        """Fill out the posting form with configuration details."""
        if not self.agent:
            raise ValueError("Agent not initialized.")
            
        self.agent.add_new_task(
            f"Fill in the posting form using these details: title='{self.config.title}', price='{self.config.price}', description='{self.config.description}', "
            f"and set the item condition to the option closest to '{self.config.condition}' (if the condition is already filled, do not change it). "
            f"For location put the city from: '{self.config.address}'. "
            f"For the zip code, put the postal code from: '{self.config.address}'. "
            f"If the site provides suggestions or auto-complete for location, select the best matching option for '{self.config.address}'. "
            f"Proceed through the location page and continue until you reach the image upload page."
            f"if the page asks for the neighbourhood, select the first option."
            f"if the page asks for 'choose the location that fits best:', select the first option."
        )
        ok, _ = await agent_run(
            self.agent, 
            max_steps=30, 
            timeout=self.config.t_long, 
            phase="Fill posting form and continue"
        )
        return ok
        
    async def upload_images(self, image_paths: list[str]) -> bool:
        """Upload images to the posting."""
        # If no images specified, nothing to do
        if not image_paths:
            print("[images] No images to upload.")
            return True

        # Use a fresh agent instance for the upload phase to avoid EventBus name collisions
        task = (
            "You are on the Craigslist image upload page for the current post. "
            "If the drag-and-drop uploader is visible, prefer clicking the 'Use classic image uploader' link if the file picker is not visible. "
            f"Upload all of the following image files from the local filesystem using the file input control (type='file'): {', '.join(image_paths)}. "
            "If multiple selection is supported, select them all at once; otherwise, upload them sequentially. "
            "Wait until the thumbnails/previews appear and all uploads complete. "
            "Finally click the 'done with images' button to continue. "
            "Do not navigate away from the image upload page until uploads complete."
            "IF NO IMAGES ARE SHOWN ON THE PAGE AFTER YOU UPLOAD, RETRY THE UPLOAD PROCESS UNTIL THEY APPEAR OR YOU TIME OUT."
        )
        agent = self.create_agent(task, available_file_paths=image_paths)

        ok, _ = await agent_run(
            agent,
            max_steps=40,
            timeout=self.config.t_long,
            phase="Upload images"
        )
        return ok

    async def publish_post(self) -> bool:
        """Click publish on the post preview page and confirm."""
        task = (
            "You are on the Craigslist post preview page. "
            "Click the 'publish' button. If any confirmation dialog or secondary 'publish'/'confirm' "
            "button appears, confirm it. Wait until there is a clear indication the post is published "
            "(e.g., navigated to the manage posting page, a success message, or the publish button is gone/disabled). "
            "Then stop."
        )
        agent = self.create_agent(task)
        ok, _ = await agent_run(
            agent,
            max_steps=15,
            timeout=self.config.t_med,
            phase="Publish post"
        )
        return ok
