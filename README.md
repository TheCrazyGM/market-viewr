# Market-Viewr

A simple Flask web application for viewing candlestick market data and trade history for Hive-Engine smart contract tokens.

## Features

- View a list of all Hive-Engine tokens
- Display candlestick charts for token market data
- View recent trade history with buy/sell indicators
- View token information and richlist
- Dark mode support with theme toggle
- Responsive design with Bootstrap 5

## Installation

1. Clone this repository
```bash
git clone https://github.com/TheCrazyGM/market-viewr.git
cd market-viewr
```

2. Create and activate a virtual environment (recommended)
```bash
# Create a virtual environment
python3 -m venv .venv

# Activate the virtual environment
# On Linux/Mac:
source .venv/bin/activate
# On Windows:
# .venv\Scripts\activate
```

3. Install dependencies
```bash
pip install -r requirements.txt
```

4. Run the application
```bash
python app.py
```

5. Open your browser and navigate to `http://localhost:9000`

## Routes

- `/` - Home page with token list
- `/market/<token>` - View candlestick chart and trade history for a specific token
- `/view/<token>` - View token information and richlist

## Technologies Used

- Flask
- Bootstrap 5
- Plotly.js for interactive charts
- Hive-Engine API for market data
- Pandas for data processing

## Features in Detail

### Trade History
The application now displays recent trade history for each token, showing:
- Date/time of the trade
- Type of trade (BUY/SELL)
- Account that made the trade
- Quantity, price, and volume of the trade

### Dark Mode
- Toggle between light and dark themes with the sun/moon button
- Theme preference is saved in local storage
- Charts and tables automatically adjust to the selected theme

## License

See the LICENSE file for details.

## Made with ❤️ by thecrazygm
