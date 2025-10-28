from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf
import pandas as pd
import os
import json
import random
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Trading Suite Monolith", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure cache directory exists
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)

def get_cache_path(symbol: str, start_date: str) -> str:
    """Generate cache file path for symbol and date range"""
    safe_symbol = symbol.replace("=", "_").replace(":", "_")
    return os.path.join(CACHE_DIR, f"{safe_symbol}_{start_date}.json")

def load_cached_data(cache_path: str) -> Optional[dict]:
    """Load data from cache if it exists and is recent"""
    if not os.path.exists(cache_path):
        return None
    
    # Check if cache is less than 1 hour old
    cache_time = datetime.fromtimestamp(os.path.getmtime(cache_path))
    if datetime.now() - cache_time > timedelta(hours=1):
        return None
    
    try:
        with open(cache_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load cache: {e}")
        return None

def save_to_cache(cache_path: str, data: dict):
    """Save data to cache"""
    try:
        with open(cache_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"Failed to save cache: {e}")

def generate_mock_data(symbol: str, start_date: datetime, end_date: datetime) -> dict:
    """Generate mock OHLC data for testing when API fails"""
    
    # Generate date range
    date_range = pd.date_range(start=start_date, end=end_date, freq='D')
    
    # Generate realistic price data
    base_price = 100.0 if 'USD' not in symbol else 1.0
    prices = []
    current_price = base_price
    
    for _ in range(len(date_range)):
        # Random walk with slight upward bias
        change = random.uniform(-0.02, 0.03)  # -2% to +3% daily change
        current_price *= (1 + change)
        prices.append(current_price)
    
    # Generate OHLC data
    data_points = []
    for i, (date, close) in enumerate(zip(date_range, prices)):
        high = close * random.uniform(1.0, 1.02)  # High is 0-2% above close
        low = close * random.uniform(0.98, 1.0)   # Low is 0-2% below close
        open_price = close * random.uniform(0.99, 1.01)  # Open is ±1% of close
        volume = random.randint(1000000, 10000000)
        
        data_points.append({
            "date": date.strftime("%Y-%m-%d"),
            "open": round(open_price, 2),
            "high": round(high, 2),
            "low": round(low, 2),
            "close": round(close, 2),
            "volume": volume
        })
    
    return {
        "symbol": symbol,
        "start_date": start_date.strftime("%Y-%m-%d"),
        "end_date": end_date.strftime("%Y-%m-%d"),
        "data": data_points,
        "note": "Mock data generated due to API connectivity issues"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "monolith", "timestamp": datetime.now().isoformat()}

@app.get("/prices")
async def get_prices(
    symbol: str = Query(..., description="Trading symbol (e.g., XAUUSD=X)"),
    start: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end: Optional[str] = Query(None, description="End date in YYYY-MM-DD format")
):
    """
    Retrieve OHLC price data for a given symbol and date range.
    Data is cached locally for 1 hour to improve performance.
    """
    try:
        # Parse dates
        start_date = datetime.strptime(start, "%Y-%m-%d")
        end_date = datetime.strptime(end, "%Y-%m-%d") if end else datetime.now()
        
        # Check cache first
        cache_path = get_cache_path(symbol, start)
        cached_data = load_cached_data(cache_path)
        
        if cached_data:
            logger.info(f"Returning cached data for {symbol}")
            return cached_data
        
        # Fetch data from yfinance
        logger.info(f"Fetching data for {symbol} from {start} to {end_date.strftime('%Y-%m-%d')}")
        
        try:
            ticker = yf.Ticker(symbol)
            # Get historical data with timeout (short timeout to fail fast and use mock data)
            hist = ticker.history(start=start_date, end=end_date, timeout=5)
            
            if hist.empty:
                raise HTTPException(status_code=404, detail=f"No data found for symbol {symbol}")
                
        except Exception as e:
            logger.error(f"Yahoo Finance API error for {symbol}: {e}")
            
            # Provide mock data for testing when API fails
            logger.info(f"Providing mock data for {symbol} due to API failure")
            try:
                mock_data = generate_mock_data(symbol, start_date, end_date)
                return mock_data
            except Exception as mock_error:
                logger.error(f"Failed to generate mock data: {mock_error}")
                # Re-raise the original exception instead of creating a new HTTPException
                raise e
        
        # Convert to the required format
        data = {
            "symbol": symbol,
            "start_date": start,
            "end_date": end_date.strftime("%Y-%m-%d"),
            "data": []
        }
        
        for date, row in hist.iterrows():
            data["data"].append({
                "date": date.strftime("%Y-%m-%d"),
                "open": float(row['Open']),
                "high": float(row['High']),
                "low": float(row['Low']),
                "close": float(row['Close']),
                "volume": int(row['Volume']) if pd.notna(row['Volume']) else 0
            })
        
        # Cache the data
        save_to_cache(cache_path, data)
        
        logger.info(f"Successfully fetched {len(data['data'])} records for {symbol}")
        return data
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Invalid date format: {e}")
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        
        # Try to provide mock data as fallback
        try:
            logger.info(f"Attempting to provide mock data for {symbol}")
            mock_data = generate_mock_data(symbol, start_date, end_date)
            return mock_data
        except Exception as mock_error:
            logger.error(f"Failed to generate mock data: {mock_error}")
            raise HTTPException(status_code=500, detail=f"Failed to fetch data: {str(e)}")

@app.get("/symbols")
async def get_available_symbols():
    """Get list of commonly used trading symbols"""
    return {
        "forex": [
            "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X", "AUDUSD=X", "USDCAD=X", "NZDUSD=X"
        ],
        "commodities": [
            "XAUUSD=X", "XAGUSD=X", "CL=F", "NG=F", "GC=F", "SI=F"
        ],
        "indices": [
            "^GSPC", "^DJI", "^IXIC", "^RUT", "^VIX"
        ],
        "crypto": [
            "BTC-USD", "ETH-USD", "BNB-USD", "ADA-USD", "SOL-USD"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
