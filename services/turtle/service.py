from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import numpy as np
import logging
from typing import Dict
import sys
import os

# Add the common utils to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common'))

from utils import PriceDataFetcher, TechnicalIndicators, SignalProcessor, MarketAnalyzer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Turtle Strategy Service", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TurtleStrategy:
    """Turtle trading strategy using Donchian channel breakouts"""
    
    def __init__(self, monolith_url: str = "http://monolith:8000"):
        self.data_fetcher = PriceDataFetcher(monolith_url)
        self.entry_period = 20  # Donchian entry period (Turtle)
        self.exit_period = 10   # Donchian exit period (Turtle)
        
    def calculate_donchian_channels(self, df: pd.DataFrame, period: int) -> pd.DataFrame:
        """Calculate Donchian channels (high/low over period)"""
        df[f'donchian_high_{period}'] = df["high"].rolling(window=period).max()
        df[f'donchian_low_{period}'] = df["low"].rolling(window=period).min()
        return df
    
    def generate_signal(self, df: pd.DataFrame) -> Dict:
        """Generate trading signal based on Donchian channel breakouts"""
        if len(df) < max(self.entry_period, self.exit_period) + 1:
            return {
                "signal": "FLAT",
                "confidence": 0.0,
                "sl_pct": 0.0,
                "tp_multiple": 0.0,
                "rationale": ["Insufficient data for signal generation"]
            }
        
        # Calculate Donchian channels
        df = self.calculate_donchian_channels(df, self.entry_period)
        df = self.calculate_donchian_channels(df, self.exit_period)
        
        # Get current values
        current_price = df["close"].iloc[-1]
        entry_high = df[f'donchian_high_{self.entry_period}'].iloc[-1]
        entry_low = df[f'donchian_low_{self.entry_period}'].iloc[-1]
        exit_high = df[f'donchian_high_{self.exit_period}'].iloc[-1]
        exit_low = df[f'donchian_low_{self.exit_period}'].iloc[-1]
        
        # Get previous values for change detection
        prev_price = df["close"].iloc[-2]
        prev_entry_high = df[f'donchian_high_{self.entry_period}'].iloc[-2]
        prev_entry_low = df[f'donchian_low_{self.entry_period}'].iloc[-2]
        
        # Calculate ATR for stop loss
        atr = TechnicalIndicators.atr(df["high"], df["low"], df["close"], 14).iloc[-1]
        
        # Analyze market conditions
        trend_analysis = MarketAnalyzer.analyze_trend(df)
        volatility_analysis = MarketAnalyzer.analyze_volatility(df)
        
        # Determine signal
        signal = "FLAT"
        rationale = []
        signal_strength = 0.5
        
        # Check for entry breakouts
        if current_price >= entry_high and prev_price < prev_entry_high:
            signal = "LONG"
            rationale.append(f"Price broke above {self.entry_period}-day high")
            rationale.append("Turtle entry signal triggered")
        elif current_price <= entry_low and prev_price > prev_entry_low:
            signal = "SHORT"
            rationale.append(f"Price broke below {self.entry_period}-day low")
            rationale.append("Turtle entry signal triggered")
        
        # Check for exit signals
        if signal != "FLAT":
            if signal == "LONG" and current_price <= exit_low:
                signal = "FLAT"
                rationale.append(f"Price dropped below {self.exit_period}-day low")
                rationale.append("Turtle exit signal triggered")
            elif signal == "SHORT" and current_price >= exit_high:
                signal = "FLAT"
                rationale.append(f"Price rose above {self.exit_period}-day high")
                rationale.append("Turtle exit signal triggered")
        
        # Calculate confidence
        if signal != "FLAT":
            # Channel width indicates breakout strength
            channel_width = (entry_high - entry_low) / current_price
            if channel_width > 0.05:  # 5% channel
                signal_strength += 0.2
                rationale.append("Wide channel indicates strong breakout")
            else:
                signal_strength -= 0.1
                rationale.append("Narrow channel may indicate weak breakout")
            
            # Adjust based on trend alignment
            if signal == "LONG" and trend_analysis["direction"] == "UP":
                signal_strength += 0.2
                rationale.append("Trend analysis confirms bullish direction")
            elif signal == "SHORT" and trend_analysis["direction"] == "DOWN":
                signal_strength += 0.2
                rationale.append("Trend analysis confirms bearish direction")
            elif signal != "FLAT":
                signal_strength -= 0.1
                rationale.append("Trend analysis conflicts with signal")
        
        # Adjust based on volatility
        if volatility_analysis["level"] == "NORMAL":
            signal_strength += 0.1
            rationale.append("Normal volatility conditions")
        elif volatility_analysis["level"] == "HIGH":
            signal_strength -= 0.1
            rationale.append("High volatility reduces signal reliability")
        
        # Calculate confidence
        market_conditions = {
            "volatility_factor": volatility_analysis["factor"],
            "trend_strength": trend_analysis["strength"]
        }
        
        confidence = SignalProcessor.calculate_confidence(signal_strength, market_conditions)
        
        # Calculate stop loss (Turtle uses 2*ATR)
        sl_pct = 0.025  # Default 2.5%
        tp_multiple = 2.0  # Turtle typically uses 2:1 R/R
        
        if atr > 0:
            # Use 2*ATR as stop loss (Turtle rule)
            atr_sl_pct = (atr * 2) / current_price
            sl_pct = max(0.02, min(0.06, atr_sl_pct))  # Between 2% and 6%
            rationale.append(f"Stop loss set at 2*ATR: {sl_pct:.3f}")
        
        return SignalProcessor.format_signal_response(
            signal, confidence, sl_pct, tp_multiple, rationale
        )

# Initialize strategy
strategy = TurtleStrategy()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "turtle", "timestamp": pd.Timestamp.now().isoformat()}

@app.post("/signal")
async def get_signal(request: Dict):
    """
    Generate Turtle trading signal
    
    Input:
    {
        "symbol": "XAUUSD=X",
        "min_conf": 0.7
    }
    
    Output:
    {
        "signal": "LONG|SHORT|FLAT",
        "confidence": 0.82,
        "sl_pct": 0.025,
        "tp_multiple": 2.0,
        "rationale": ["explanation strings"]
    }
    """
    try:
        symbol = request.get("symbol")
        min_conf = request.get("min_conf", 0.5)
        
        if not symbol:
            raise HTTPException(status_code=400, detail="Symbol is required")
        
        logger.info(f"Generating Turtle signal for {symbol}")
        
        # Fetch price data
        df = await strategy.data_fetcher.get_price_data(symbol)
        if df is None or len(df) < 50:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {symbol}")
        
        # Generate signal
        result = strategy.generate_signal(df)
        
        # Validate signal meets minimum confidence
        if not SignalProcessor.validate_signal(result["signal"], result["confidence"], min_conf):
            result["signal"] = "FLAT"
            result["rationale"].append(f"Signal confidence {result['confidence']} below minimum {min_conf}")
        
        logger.info(f"Turtle signal for {symbol}: {result['signal']} (confidence: {result['confidence']})")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating Turtle signal: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate signal: {str(e)}")

@app.get("/parameters")
async def get_parameters():
    """Get current strategy parameters"""
    return {
        "entry_period": strategy.entry_period,
        "exit_period": strategy.exit_period,
        "description": "Turtle trading strategy using Donchian channel breakouts"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
