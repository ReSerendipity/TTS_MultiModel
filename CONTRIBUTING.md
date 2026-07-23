# Contributing to TTS MultiModel

Thank you for your interest in contributing to TTS MultiModel! This guide will help you get started.

## Ways to Contribute

- **Bug Reports**: Submit issues with detailed reproduction steps
- **Feature Requests**: Open an issue with the `enhancement` label
- **Code Contributions**: Fork → Branch → Commit → Push → Pull Request
- **Documentation**: Fix typos, add examples, improve translations
- **Testing**: Write and improve test coverage
- **Translations**: Help translate the web interface to new languages

## Good First Issues

We label issues that are great for newcomers:

- 🔖 [`good-first-issue`](https://github.com/ReSerendipity/TTS_MultiModel/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) — Simple bug fixes or documentation improvements
- 🏷️ [`help-wanted`](https://github.com/ReSerendipity/TTS_MultiModel/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) — Features that need community help

## Development Setup

### Prerequisites

- **Python**: 3.10+ (3.12 recommended)
- **GPU**: NVIDIA (CUDA) / Apple Silicon (MPS) with 6GB+ VRAM (for testing generation features)
- **Git**: Latest version

### Quick Setup

```bash
# Clone the repository
git clone https://github.com/ReSerendipity/TTS_MultiModel.git
cd TTS_MultiModel

# Create a virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# Linux/Mac:
source .venv/bin/activate

# Install the package in development mode
pip install -e ".[dev]"

# Or install dependencies manually
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cuff
pip install ruff

# Run tests (unit tests only, skip GPU-dependent tests)
pytest tests/ -v -k "not gpu and not cuda and not vram" -m "not integration"

# Run linter
ruff check bin/integrated_app/ scripts/

# Run formatter
ruff format bin/integrated_app/ scripts/
```

### Project Structure Overview

```
TTS_MultiModel/
├── bin/integrated_app/        # Main application
│   ├── engines/               # TTS engine implementations
│   │   ├── voxcpm2/           # VoxCPM2 engine
│   │   └── indextts2_engine.py
│   ├── routes/                # API route handlers
│   ├── templates/             # Jinja2 HTML templates
│   ├── training/              # LoRA fine-tuning
│   ├── middleware/             # HTTP middleware
│   └── locales/               # i18n translations
├── tests/                     # Test suite
├── docs/                      # Documentation
└── examples/                  # API usage examples
```

For detailed architecture, see [docs/PROJECT_ARCHITECTURE.md](docs/PROJECT_ARCHITECTURE.md).

## Code Style

- Follow PEP 8 conventions
- Use `ruff` for linting and formatting
- Line length: 120 characters
- Type hints are encouraged for public APIs
- Use `snake_case` for Python variables/functions, `PascalCase` for classes
- Use `namespace.sub.key` format for i18n keys

## Pull Request Process

1. **Fork** the repository
2. **Create a feature branch**: `git checkout -b feature/your-feature-name`
3. **Make your changes** with clear, concise commits
4. **Add tests** for new functionality
5. **Run the test suite**: `pytest tests/ -v`
6. **Run linter**: `ruff check bin/integrated_app/ scripts/`
7. **Submit a Pull Request** with a clear description

### Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/) format:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `refactor:` Code refactoring
- `test:` Test additions/changes
- `chore:` Build/process changes
- `i18n:` Translation updates

Examples:
```
feat(voxcpm2): add streaming generation support
fix(auth): prevent timing attacks on token comparison
docs: update model download guide with correct repo IDs
i18n: add Korean translations for help page
```

## Bug Reports

When filing a bug report, please include:

1. **Environment**: OS, Python version, GPU type, PyTorch version
2. **Steps to reproduce**: Clear, step-by-step instructions
3. **Expected behavior**: What you expected to happen
4. **Actual behavior**: What actually happened
5. **Logs**: Relevant log output from `logs/app.log`

## Feature Requests

When suggesting a feature, please include:

1. **Use case**: Why is this feature needed?
2. **Proposed solution**: How should it work?
3. **Alternatives**: Any alternative approaches considered
4. **Related issues**: Links to similar requests if any

## Translations

We welcome translations for the web interface! Currently supported:

- Chinese (zh) - Complete
- English (en) - Complete
- Japanese (ja) - Complete
- Korean (ko) - Complete

To add a new language:

1. Create a new JSON file in `bin/integrated_app/locales/` (e.g., `fr.json`)
2. Follow the existing translation file format from `zh.json` as reference
3. Submit a PR with the new translation

## Architecture Decisions

For significant changes (new engines, major refactors, new subsystems):

1. **Open an Issue first** to discuss the proposed change
2. Wait for maintainer feedback before starting implementation
3. Large PRs are harder to review — consider breaking them into smaller, reviewable chunks

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](LICENSE).

## Getting Help

- **Issues**: For bugs and feature requests
- **Discussions**: For questions and general discussion
- **Code Review**: Maintainers will review PRs within a reasonable timeframe
# Contributing to TTS MultiModel

Thank you for your interest in contributing to TTS MultiModel! This guide will help you get started.

## 🌟 Ways to Contribute

- **Bug Reports**: Submit issues with detailed reproduction steps
- **Feature Requests**: Open an issue with the `enhancement` label
- **Code Contributions**: Fork → Branch → Commit → Push → Pull Request
- **Documentation**: Fix typos, add examples, improve translations
- **Testing**: Write and improve test coverage

## 🛠️ Development Setup

```bash
# Clone the repository
git clone https://github.com/ReSerendipity/TTS_MultiModel.git
cd TTS_MultiModel

# Install dependencies
pip install -r requirements.txt

# Install dev dependencies
pip install pytest pytest-asyncio pytest-cov ruff

# Run tests
pytest tests/ -v -k "not gpu and not cuda and not vram" -m "not integration"

# Run linter
ruff check bin/integrated_app/ scripts/

# Run formatter
ruff format bin/integrated_app/ scripts/
```

## 📋 Code Style

- Follow PEP 8 conventions
- Use `ruff` for linting and formatting
- Line length: 120 characters
- Type hints are encouraged for public APIs

## 🔄 Pull Request Process

1. **Fork** the repository
2. **Create a feature branch**: `git checkout -b feature/your-feature-name`
3. **Make your changes** with clear, concise commits
4. **Add tests** for new functionality
5. **Run the test suite**: `pytest tests/ -v`
6. **Run linter**: `ruff check bin/integrated_app/ scripts/`
7. **Submit a Pull Request** with a clear description

### Commit Messages

Use conventional commit format:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `refactor:` Code refactoring
- `test:` Test additions/changes
- `chore:` Build/process changes

## 🐛 Bug Reports

When filing a bug report, please include:

1. **Environment**: OS, Python version, GPU type, PyTorch version
2. **Steps to reproduce**: Clear, step-by-step instructions
3. **Expected behavior**: What you expected to happen
4. **Actual behavior**: What actually happened
5. **Logs**: Relevant log output from `logs/app.log`

## 💡 Feature Requests

When suggesting a feature, please include:

1. **Use case**: Why is this feature needed?
2. **Proposed solution**: How should it work?
3. **Alternatives**: Any alternative approaches considered

## 🌍 Translations

We welcome translations for the web interface! Currently supported:

- Chinese (zh) - Complete
- English (en) - Complete
- Japanese (ja) - Complete
- Korean (ko) - Complete

To add a new language:

1. Create a new translation file in `bin/integrated_app/locales/`
2. Follow the existing translation file format
3. Submit a PR with the new translation

## 📜 License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.
