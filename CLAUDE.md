# CLAUDE.md - Market-viewr Assistant Guide

## Project Commands
- **Setup**: `python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
- **Run**: `python app.py` (runs on port 9000 in debug mode)
- **Linting**: `flake8 .` (recommended - not yet configured)
- **Type checking**: `mypy .` (recommended - not yet configured)
- **Testing**: `pytest` (recommended - not yet configured)

## Code Style Guidelines
- **Python version**: 3.13+
- **Formatting**: Follow PEP 8 (4-space indentation, max 100 char line length)
- **Docstrings**: Use docstrings for functions with descriptive explanations
- **Imports**: Group standard library, third-party, and local imports with spacing
- **Error handling**: Use try/except with specific exceptions and error messages
- **Types**: Although no type checking is configured, use type hints
- **Naming**: Use snake_case for variables/functions, PascalCase for classes
- **Functions**: Focus on single responsibility with descriptive names

## Application Context
Market-viewr displays and analyzes Hive-Engine blockchain tokens with price charts, order books, and token information. The app uses Flask, Plotly for visualization, and the hiveengine API library.