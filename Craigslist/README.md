# Craigslist Post Helper (browser-use)

Automates navigating Craigslist to create a posting using the browser-use Agent with OpenAI or Google Gemini (configured via environment).

**✨ Recently Updated:** The codebase has been completely refactored for better maintainability, readability, and developer experience. The application is now organized into modular components while maintaining the same user interface.

## 🏗️ Architecture

The application is now organized into clean, modular components:

```
├── src/                    # Main application modules
│   ├── __init__.py        # Package initialization
│   ├── config.py          # Configuration management
│   ├── cookies.py         # Cookie persistence & session management
│   ├── auth.py            # Authentication & login detection
│   ├── images.py          # Image file resolution & handling
│   ├── agent.py           # Browser automation workflows
│   └── main.py            # Main application entry point
├── script.py              # Entry point (same interface as before)
├── test_integration.py    # Comprehensive integration tests
├── test_gemini_key.py     # API key validation utility
└── cookies/               # Session storage directory
```

## Prerequisites
- Python 3.10+
- Environment configuration (ENV-only):
  - Set `OPENAI_API_KEY` (OpenAI GPT) or `GOOGLE_API_KEY`/`GEMINI_API_KEY` (Gemini)
  - Set `LLM_PROVIDER` to `openai` or `google` (or `auto` to prefer OpenAI if available)
  - Set `LLM_MODEL` (e.g., `gpt-4.1` or `gemini-2.5-flash`)
  - Other settings: `EMAIL`, `CATEGORY`, `POSTING_TITLE`, `CONDITION`, `PRICE`, `CITY`, `POSTAL_CODE`, `DESCRIPTION`, `IMAGES`, `HEADLESS`, timeouts.
  - See `.env.example` for all required variables.

## Setup
```bash
# From project root
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Optionally, copy env template
cp .env.example .env
# then edit .env and add your API key
```

## Testing

Test your setup and verify all modules are working:

```bash
# Run comprehensive integration tests
python test_integration.py

# Test API key configuration
python test_gemini_key.py
```

## Run
```bash
# Configure environment in .env (see .env.example), then:
python script.py
# or with uv:
uv run script.py
```

Configuration is ENV-only (no CLI flags). Adjust values in `.env`.

### LLM selection (ENV-only)
Select provider/model using environment variables:

```bash
# OpenAI (GPT)
export OPENAI_API_KEY=sk-...
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4.1
python script.py

# Google Gemini
export GOOGLE_API_KEY=your_gemini_key   # or: export GEMINI_API_KEY=...
export LLM_PROVIDER=google
export LLM_MODEL=gemini-2.5-flash
python script.py
```

## How it works
1. **Session Management**: Loads cookies for the provided email (if found).
2. **Authentication**: Checks if you are logged in by visiting the account area and looking for "make new post" or "log out".
3. **Login Flow**: If not logged in, starts the email login (magic link) flow and prompts you to paste the link from your inbox.
4. **Form Automation**: Navigates to post creation, fills the form, and uploads images.
5. **Cookie Persistence**: Saves cookies per email under `cookies/<email>.json` for future sessions.

## 🆕 Improvements in This Version

### Code Organization
- **Modular Design**: Code split into focused, single-responsibility modules
- **Clean Architecture**: Clear separation between configuration, authentication, image handling, and browser automation
- **Type Hints**: Better code documentation and IDE support
- **Error Handling**: Improved error messages and graceful failure handling

### Developer Experience
- **Integration Testing**: Comprehensive test suite to verify all components
- **Better Logging**: Enhanced logging with consistent formatting and categories
- **Documentation**: Improved inline documentation and module docstrings
- **Maintainability**: Easier to modify, extend, and debug individual components

### Reliability
- **Session Management**: More robust cookie handling and session persistence
- **Authentication**: Improved login detection with multiple fallback strategies
- **Image Resolution**: Enhanced image file discovery across common directories
- **Error Recovery**: Better error handling and recovery mechanisms

## Module Details

### `src/config.py`
Handles all configuration strictly via environment variables (.env). No CLI flags are used.

### `src/cookies.py`
Manages browser session persistence with robust cookie save/load functionality.

### `src/auth.py`
Handles Craigslist authentication detection and magic link workflow management.

### `src/images.py`
Resolves image file paths from various common locations and validates image availability.

### `src/agent.py`
Manages the browser-use agent workflows for different phases of the posting process.

### `src/main.py`
Orchestrates the entire application flow, coordinating all modules for the complete posting workflow.

## Troubleshooting
- If phases time out, increase `CRAIGS_TIMEOUT_LONG` in your `.env`.
- If images aren't found, check paths or place files under `images/`, your `Downloads/`, or provide absolute paths.
- If login detection seems off, ensure the account page shows "make new post" when logged in.
- Run `python test_integration.py` to verify all components are working correctly.
- Use `python test_gemini_key.py` or `python test_openai_key.py` to test API key configuration.

## Development

The new modular structure makes it easy to:
- Add new features by extending existing modules
- Debug specific components in isolation  
- Write focused unit tests for individual modules
- Customize behavior without affecting other parts of the system

Each module is designed to be testable and maintainable, with clear interfaces and minimal coupling between components.
