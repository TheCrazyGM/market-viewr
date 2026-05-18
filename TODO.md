# Market-Viewr Refactoring & Reorganization Scope

## Objective

Refactor the monolithic `app.py` (~1400 lines) into a modular, maintainable structure under a new `src/viewr` package. Establish clear domain boundaries, improve separation of concerns, and clean up deprecated files like `requirements.txt`.

## Proposed Architecture

```text
market-viewr/
├── src/
│   └── viewr/
│       ├── __init__.py           # Flask app factory (create_app)
│       ├── config.py             # Application configuration (Redis/Cache settings)
│       ├── extensions.py         # Flask extensions (cache instantiation)
│       ├── api/                  # External API Clients
│       │   ├── __init__.py
│       │   └── hive_engine.py    # Node selection, Api/Market proxy wrappers
│       ├── services/             # Core Business Logic (Data Fetching & Caching)
│       │   ├── __init__.py
│       │   ├── market.py         # get_market_data, get_trade_history, get_orderbook
│       │   ├── pools.py          # get_lp_pools, get_lp_positions
│       │   └── tokens.py         # get_tokens, get_token_info, get_richlist
│       ├── routes/               # Flask Blueprints (Controllers)
│       │   ├── __init__.py
│       │   ├── api.py            # /health, /api/chart/*, /api/orderbook/*
│       │   ├── main.py           # /, /market/*, /view/*, /richlist/*
│       │   └── pools.py          # /lp/*
│       └── utils/                # Helper Functions
│           ├── __init__.py
│           ├── formatters.py     # Jinja2 template filters (fmt, timestamp_to_date)
│           ├── security.py       # sanitize_symbol, is_valid_image_url
│           └── errors.py         # Custom error handlers (404, 500, generic)
├── static/                       # Unchanged
├── templates/                    # Unchanged
├── clear_cache.py                # Updated to import from src.viewr
├── warm_cache.py                 # Updated to import from src.viewr
├── pyproject.toml                # Updated to define src layout
├── Makefile                      # Updated to use src layout
└── uv.lock                       # Managed by uv
```

## Phase 1: Environment & Project Setup

- [ ] Delete `requirements.txt` (as `uv.lock` and `pyproject.toml` are the source of truth).
- [ ] Create the new directory structure (`src/viewr/` and subdirectories).
- [ ] Update `pyproject.toml` to recognize the `src` layout.

## Phase 2: Core Infrastructure (Extensions & Config)

- [ ] Extract cache configuration and Redis setup into `src/viewr/config.py`.
- [ ] Initialize the `Cache` object in `src/viewr/extensions.py` to avoid circular imports.
- [ ] Implement the Application Factory pattern (`create_app`) in `src/viewr/__init__.py`.

## Phase 3: Utilities & API Clients

- [ ] Extract template filters (`fmt`, `timestamp_to_date`) to `src/viewr/utils/formatters.py`.
- [ ] Extract security functions (`sanitize_symbol`, `is_valid_image_url`) to `src/viewr/utils/security.py`.
- [ ] Extract error handlers to `src/viewr/utils/errors.py`.
- [ ] Extract Hive-Engine API node selection, retry logic, and proxy wrappers (`get_he_api`, `he_market`, etc.) to `src/viewr/api/hive_engine.py`.

## Phase 4: Business Logic (Services)

- [ ] Move token-related data functions (`get_tokens`, `get_token_info`, `get_richlist`) to `src/viewr/services/tokens.py`.
- [ ] Move market-related data functions (`get_trade_history`, `get_market_data`) to `src/viewr/services/market.py`.
- [ ] Move liquidity pool data functions (`get_lp_pools_for_token`, `get_lp_pool`, `get_lp_positions`) to `src/viewr/services/pools.py`.

## Phase 5: Routing (Blueprints)

- [ ] Convert main UI routes (`/`, `/market/`, `/view/`, `/richlist/`) into a Flask Blueprint in `src/viewr/routes/main.py`.
- [ ] Convert API routes (`/api/chart/`, `/api/orderbook/`, `/health`) into an API Blueprint in `src/viewr/routes/api.py`.
- [ ] Convert LP routes (`/lp/`) into a Blueprint in `src/viewr/routes/pools.py`.
- [ ] Register all blueprints within `create_app` in `src/viewr/__init__.py`.

## Phase 6: Scripts & Polish

- [ ] Update `clear_cache.py` to use the `create_app` factory context.
- [ ] Update `warm_cache.py` to use the `create_app` factory context.
- [ ] Update `Makefile` to ensure `lint`, `format`, and `dev-setup` target the new `src/` directory appropriately.
- [ ] Verify `app.py` in the root is deleted or replaced with a simple runner script (e.g., `wsgi.py` or just `import from viewr`).
- [ ] Run `make lint` and run manual tests to ensure the application starts and pages load correctly.
