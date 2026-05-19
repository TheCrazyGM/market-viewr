# Market-Viewr

A modern, modular Flask web application for viewing candlestick market data, trade history, and liquidity pool statistics for Hive-Engine smart contract tokens.

## Features

- **Token Explorer:** View a paginated list of all Hive-Engine tokens with search functionality.
- **Market Data:** Interactive candlestick charts (Plotly) and detailed trade history.
- **Richlists:** View top token holders and export full richlists to CSV.
- **Liquidity Pools:** Explore market pools, view pool depth, prices, and top liquidity provider positions.
- **Caching:** Robust caching layer using Redis (with SimpleCache fallback) for high performance.
- **Responsive UI:** Modern design using Bootstrap 5 with native dark mode support.

## Project Structure

The application follows a modular "Application Factory" pattern:

```text
src/viewr/
├── api/          # Hive-Engine RPC and history API clients
├── routes/       # Flask Blueprints (main, api, pools)
├── services/     # Core business logic and data fetching
├── utils/        # Formatting, security sanitization, and error handlers
├── config.py     # Environment-based configuration
└── extensions.py # Flask extension initializations (Cache)
```

## Installation & Setup

This project uses [uv](https://github.com/astral-sh/uv) for fast, reliable Python package and environment management.

1. **Clone the repository:**

   ```bash
   git clone https://github.com/TheCrazyGM/market-viewr.git
   cd market-viewr
   ```

2. **Initialize the environment:**

   ```bash
   # Sync dependencies and create .venv automatically
   uv sync
   ```

3. **Configure Redis (Optional but Recommended):**
   The app defaults to `redis://localhost:6379/1`. If Redis is unavailable, it will automatically fall back to an in-memory cache.

## Running the Application

You can use the provided `Makefile` or run it directly with `uv`.

- **Using Makefile:**

  ```bash
  make run
  ```

- **Using uv:**

  ```bash
  uv run python wsgi.py
  ```

The application will be available at `http://localhost:9000`.

## Routes & API

### User Interface

- `/` - Home page with token list and search.
- `/market/<token>` - Interactive charts and recent trade history.
- `/view/<token>` - Detailed token info and top 100 richlist.
- `/richlist/<token>` - Full searchable richlist.
- `/lp/<token>` - List of liquidity pools involving the token.
- `/lp/<base>/<quote>` - Detailed liquidity pool statistics and provider positions.

### API Endpoints

- `/health` - System health check and dependency status.
- `/api/chart/<token>/<timeframe>` - Returns Plotly JSON for market charts.
- `/api/orderbook/<token>` - Returns complete buy/sell order books.

## Development

- **Linting:** `make lint` (uses Ruff)
- **Formatting:** `uv run ruff format .`
- **Cache Management:**
  - `uv run python clear_cache.py` - Manually purge all cached data.
  - `uv run python warm_cache.py` - Pre-fetch and cache all token richlists.

## License

See the `LICENSE` file for details.

## Made with ❤️ by thecrazygm
