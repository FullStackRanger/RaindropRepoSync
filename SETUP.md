# Setup Guide

## Quick Setup (Poetry - Recommended)

1. **Install dependencies:**
   ```bash
   cd ~/Public/Apps/Personal/toolbelt
   poetry install
   ```

2. **Set your API key:**
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   # Or add to ~/.zshrc for persistence
   ```

3. **Run a test:**
   ```bash
   poetry run medium-digest --no-ai --dry-run
   ```

4. **Run with AI:**
   ```bash
   poetry run medium-digest
   ```

## Alternative Setup (pip)

1. **Install dependencies:**
   ```bash
   cd ~/Public/Apps/Personal/toolbelt
   pip install -r requirements.txt
   ```

2. **Run the agent:**
   ```bash
   python run.py
   ```

## Development Workflow

### Running Tests
```bash
poetry run pytest
```

### Code Formatting
```bash
# Format code
poetry run black src/ tests/

# Lint code
poetry run ruff check src/ tests/

# Auto-fix linting issues
poetry run ruff check --fix src/ tests/
```

### Installing New Dependencies
```bash
# Add a production dependency
poetry add package-name

# Add a development dependency
poetry add --group dev package-name
```

## Project Structure

```
toolbelt/
├── src/medium_digest/       # Main package
│   ├── __init__.py
│   ├── main.py             # CLI entry point
│   ├── config.py           # Configuration
│   ├── fetcher.py          # RSS & content fetching
│   └── summarizer.py       # AI summarization
├── tests/                  # Test files
├── run.py                  # Convenience script
├── pyproject.toml          # Poetry config
└── requirements.txt        # Legacy pip requirements
```

## Scheduling (Optional)

To run daily automatically:

```bash
python setup_schedule.py
```

This creates a macOS launchd agent that runs at 7:00 AM daily.
