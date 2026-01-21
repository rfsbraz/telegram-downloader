# Contributing to Telegram Media Downloader

Thank you for your interest in contributing! This document provides guidelines for contributing to the project.

## Code of Conduct

This project adheres to a [Code of Conduct](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## How Can I Contribute?

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates. When creating a bug report, include:

- **Clear title and description**
- **Steps to reproduce** the issue
- **Expected vs actual behavior**
- **Environment details** (OS, Python version, Docker version)
- **Configuration** (redact sensitive information like API keys)
- **Logs** (use `docker compose logs`)

### Suggesting Enhancements

Enhancement suggestions are welcome! Please include:

- **Use case**: Why is this enhancement needed?
- **Proposed solution**: How should it work?
- **Alternatives considered**: What other approaches did you think about?

### Pull Requests

1. **Fork the repository** and create your branch from `master`
2. **Make your changes** following the code style guidelines
3. **Test your changes** thoroughly
4. **Update documentation** if needed
5. **Write clear commit messages** following the project's convention
6. **Submit a pull request** with a comprehensive description

## Development Setup

### Prerequisites

- Python 3.11+
- Docker and Docker Compose (for testing)
- Git

### Local Development

1. **Clone your fork:**
   ```bash
   git clone https://github.com/YOUR_USERNAME/telegram-downloader.git
   cd telegram-downloader
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   pip install -r requirements-dev.txt  # If exists
   ```

4. **Set up configuration:**
   ```bash
   cp config.example.toml config.toml  # If example exists
   # Edit config.toml with your Telegram API credentials
   ```

5. **Run the application:**
   ```bash
   python -m telegram_downloader.main
   ```

### Testing

```bash
# Run tests (when test suite exists)
pytest

# Run with coverage
pytest --cov=telegram_downloader

# Test Docker build
docker build -t telegram-downloader-test .
docker compose -f docker-compose.test.yml up  # If exists
```

### Documentation

Documentation is built with MkDocs Material:

```bash
# Install docs dependencies
pip install -r requirements-docs.txt

# Serve locally
mkdocs serve

# Build
mkdocs build --strict
```

## Code Style Guidelines

### Python Code

- Follow [PEP 8](https://pep8.org/) style guide
- Use type hints where appropriate
- Write docstrings for public functions and classes
- Keep functions focused and small
- Use meaningful variable names

**Example:**
```python
def download_media(
    client: Client,
    message: Message,
    destination: Path
) -> Optional[Path]:
    """Download media from a Telegram message.

    Args:
        client: Pyrogram client instance
        message: Message containing media
        destination: Target download directory

    Returns:
        Path to downloaded file, or None if no media
    """
    # Implementation...
```

### Commit Messages

Follow conventional commits format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

**Examples:**
```
feat(filters): add regex pattern support for filename filtering

Add ability to use regex patterns in addition to wildcards for more
flexible filename matching.

Closes #42
```

```
fix(daemon): handle FloodWait errors gracefully

Daemon now automatically retries after FloodWait with exponential
backoff instead of crashing.

Fixes #38
```

## Project Structure

```
telegram-downloader/
├── src/
│   └── telegram_downloader/
│       ├── __init__.py
│       ├── main.py              # Entry point
│       ├── config.py            # Configuration management
│       ├── client.py            # Telegram client wrapper
│       ├── downloader.py        # Download logic
│       ├── filters.py           # Message filters
│       ├── sources.py           # Source implementations
│       ├── organizer.py         # File organization
│       ├── daemon.py            # Daemon service
│       └── notifications.py     # Notification system
├── docs/                        # MkDocs documentation
├── examples/                    # Docker Compose examples
├── tests/                       # Test suite
├── .github/                     # GitHub templates and workflows
├── Dockerfile                   # Multi-stage Docker build
├── docker-compose.yml           # Docker Compose configuration
├── requirements.txt             # Python dependencies
├── requirements-docs.txt        # Documentation dependencies
├── mkdocs.yml                   # MkDocs configuration
└── README.md                    # Project overview
```

## Architecture Guidelines

### Core Principles

1. **Security First**: Always validate inputs, sanitize filenames, protect sessions
2. **Fail Fast**: Validate configuration at startup, not during operation
3. **Graceful Degradation**: Handle errors without crashing the daemon
4. **Clean Architecture**: Separate concerns (config, download, organization, notification)

### Key Design Patterns

- **Factory Pattern**: Source factory creates appropriate source implementations
- **Strategy Pattern**: Filters compose different matching strategies
- **Repository Pattern**: State management abstraction over SQLite
- **Observer Pattern**: Notifications observe download events

## Testing Guidelines

### What to Test

- Configuration validation
- Filter matching logic
- File organization (sanitization, conflict resolution, duplicate detection)
- Error handling (FloodWait, network errors, invalid sources)
- State persistence across restarts

### What Not to Test

- External dependencies (Pyrogram, Telegram API)
- Docker container behavior (covered by integration tests)

## Documentation Guidelines

- Update relevant documentation for any user-facing changes
- Add examples for new features
- Update configuration reference for new settings
- Keep quickstart guide up-to-date

## Questions?

- **General questions**: Use [GitHub Discussions](https://github.com/rfsbraz/telegram-downloader/discussions)
- **Bug reports**: Open an [issue](https://github.com/rfsbraz/telegram-downloader/issues)
- **Feature requests**: Open an [issue](https://github.com/rfsbraz/telegram-downloader/issues)

Thank you for contributing! 🎉
