# Contributing

Thanks for your interest in contributing! Here's everything you need to get started.

## Development Setup

```bash
# Clone and install
git clone https://github.com/rfsbraz/telegram-downloader.git
cd telegram-downloader
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install pytest pytest-cov pytest-asyncio
```

### Running Tests

```bash
make test          # all tests with coverage
make unit          # unit tests only
make integration   # integration tests only
```

### Running Locally

```bash
make run           # builds Docker image + docker compose up
# or
docker compose up --build
```

### Building Docs

```bash
pip install -r requirements-docs.txt
mkdocs serve       # local preview at http://localhost:8000
```

## Making Changes

1. Fork the repository and create a branch from `main`
2. Make your changes
3. Run `make test` and make sure everything passes
4. Update documentation if your change affects user-facing behavior
5. Open a pull request and fill in the template, including the AI use section

### Low-effort and automated PRs

Telegram Media Downloader is maintained in my spare time, and every PR takes real time to review. I'm happy to get contributions from people who use Telegram Media Downloader and want to make it better.

I will close, without review, PRs that look like contribution farming: accounts opening many PRs across unrelated projects, or changes made mainly to collect contributions rather than to fix something you ran into. This applies even when the change itself is correct.

AI-assisted PRs are fine if you've read and understood the change and can answer questions about it. Please say so in the PR.

The easiest way to get a PR merged is to start with an issue, agree on the approach there, and then open the PR.

### Commit Messages

Use [conventional commits](https://www.conventionalcommits.org/):

```
feat(filters): add regex pattern support
fix(daemon): handle FloodWait gracefully
docs: update configuration reference
chore(deps): bump pyrogram
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `ci`, `perf`, `build`

## Project Structure

```
src/
  client/          # Telegram client and download logic
  config/          # Configuration loading and validation
  daemon/          # Daemon service and health checks
  filters/         # Message filtering (extension, size, date, pattern)
  notifications/   # Discord webhooks, HTTP POST
  organization/    # File deduplication and path building
  security/        # Filename sanitization
  sources/         # Channel, group, forum topic, private chat
  state/           # SQLite-backed cursor, download history, pending queue
  main.py          # Entry point
tests/
  unit/            # Fast, no external dependencies
  integration/     # Config loading, filter chains, healthcheck
docs/              # MkDocs documentation
examples/          # Docker Compose examples
```

## Questions?

- **Bug reports and feature requests**: [Open an issue](https://github.com/rfsbraz/telegram-downloader/issues)
- **General questions**: [GitHub Discussions](https://github.com/rfsbraz/telegram-downloader/discussions)
