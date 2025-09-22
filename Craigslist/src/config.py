"""Configuration management for Craigslist Post Helper (ENV-only)."""

import os
from dataclasses import dataclass
from typing import List
from dotenv import load_dotenv

# Load environment variables from .env, if present
load_dotenv()


def env_bool(name: str, default: bool = False) -> bool:
    """Convert environment variable to boolean."""
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


def require_env(name: str) -> str:
    """Fetch a required environment variable or raise a ValueError with guidance."""
    val = os.getenv(name)
    if val is None or str(val).strip() == "":
        raise ValueError(
            f"Missing required environment variable: {name}\n"
            f"Add {name}=... to your .env file (see .env.example) and re-run."
        )
    return str(val).strip()


@dataclass
class Config:
    """Configuration object for the Craigslist posting application."""
    email: str
    category: str
    title: str
    condition: str
    price: int
    address: str
    description: str
    images: List[str]
    headless: bool
    highlight: bool
    t_short: int
    t_med: int
    t_long: int
    llm_provider: str
    llm_model: str

    def validate_api_key(self) -> tuple[str, str]:
        """Validate and return (api_key, provider) where provider is 'openai' or 'google'.

        Provider selection logic:
        - If self.llm_provider is 'openai' or 'google', require the matching key.
        - If 'auto' (default), prefer OPENAI_API_KEY if present; otherwise GOOGLE/GEMINI.
        """
        provider_pref = (self.llm_provider or "auto").strip().lower()

        def missing_key_err() -> ValueError:
            return ValueError(
                "Missing API key in environment.\n"
                "Set one of:\n"
                "- OPENAI_API_KEY (for OpenAI GPT models)\n"
                "- GOOGLE_API_KEY or GEMINI_API_KEY (for Google Gemini models)\n"
                "You can also control selection via LLM_PROVIDER=openai|google (default: auto)."
            )

        if provider_pref in {"openai", "oai", "gpt"}:
            openai_key = os.getenv("OPENAI_API_KEY")
            if openai_key:
                return openai_key, "openai"
            raise missing_key_err()

        if provider_pref in {"google", "gemini"}:
            google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if google_key:
                return google_key, "google"
            raise missing_key_err()

        # auto
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            return openai_key, "openai"
        google_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
        if google_key:
            return google_key, "google"
        raise missing_key_err()

    def log_config(self) -> None:
        """Log the effective configuration (ENV-driven)."""
        print("[config] Effective configuration:\n"
              f"  email={self.email}\n  category={self.category}\n  title={self.title}\n  price={self.price}\n"
              f"  address={self.address}\n  headless={self.headless}\n"
              f"  highlight={self.highlight}\n"
              f"  timeouts(short/med/long)={self.t_short}/{self.t_med}/{self.t_long}\n"
              f"  llm_provider={self.llm_provider}\n  llm_model={self.llm_model or '(default)'}")


def build_config() -> Config:
    """Build configuration strictly from environment variables (.env)."""
    # Required posting fields
    email = require_env("EMAIL")
    category = require_env("CATEGORY")
    title = require_env("POSTING_TITLE")
    condition = require_env("CONDITION")
    price = int(require_env("PRICE"))
    address = require_env("ADDRESS")
    description = require_env("DESCRIPTION")

    # Optional list of images (comma-separated)
    images_env = os.getenv("IMAGES", "")
    images = [s.strip() for s in images_env.split(",") if s.strip()]

    # Browser + timeouts
    headless = env_bool("HEADLESS", False)
    highlight = env_bool("HIGHLIGHT", True)
    t_short = int(os.getenv("CRAIGS_TIMEOUT_SHORT", "120"))
    t_med = int(os.getenv("CRAIGS_TIMEOUT_MED", "300"))
    t_long = int(os.getenv("CRAIGS_TIMEOUT_LONG", "600"))

    # LLM selection (ENV-required)
    llm_provider = require_env("LLM_PROVIDER").lower()
    llm_model = require_env("LLM_MODEL")

    return Config(
        email=email,
        category=category,
        title=title,
        condition=condition,
        price=price,
        address=address,
        description=description,
        images=images,
        headless=headless,
        highlight=highlight,
        t_short=t_short,
        t_med=t_med,
        t_long=t_long,
        llm_provider=llm_provider,
        llm_model=llm_model,
    )
