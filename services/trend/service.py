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

app = FastAPI(title="Trend Strategy Service", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TrendStrategy:
    """Trend following strategy using EMA crossovers and MACD confirmation"""
    
    def __init__(self, monolith_url: str = "http://monolith:8000"):
        self.data_fetcher = PriceDataFetcher(monolith_url)
        self.ema_fast = 50
        self.ema_slow = 200
        self.macd_fast = 12
        self.macd_slow = 26
        self.macd_signal = 9
        
    def generate_signal(self, df: pd.DataFrame) -> Dict:
        """Generate trading signal based on EMA crossovers and MACD"""
        if len(df) < max(self.ema_slow, self.macd_slow + self.macd_signal) + 10:
            return {
                "signal": "FLAT",
                "confidence": 0.0,
                "sl_pct": 0.0,
                "tp_multiple": 0.0,
                "rationale": ["Insufficient data for signal generation"]
            }
        
        # Calculate indicators
        close = df['close']
        ema_fast = TechnicalIndicators.ema(close, self.ema_fast)
        ema_slow = TechnicalIndicators.ema(close, self.ema_slow)
        macd_line, macd_signal_line, macd_histogram = TechnicalIndicators.macd(
            close, self.macd_fast, self.macd_slow, self.macd_signal
        )
        atr = TechnicalIndicators.atr(df['high'], df['low'], df['close'], 14)
        
        # Get current and previous values
        current_price = close.iloc[-1]
        current_ema_fast = ema_fast.iloc[-1]
        current_ema_slow = ema_slow.iloc[-1]
        prev_ema_fast = ema_fast.iloc[-2]
        prev_ema_slow = ema_slow.iloc[-2]
        
        current_macd = macd_line.iloc[-1]
        current_macd_signal = macd_signal_line.iloc[-1]
        prev_macd = macd_line.iloc[-2]
        prev_macd_signal = macd_signal_line.iloc[-2]
        current_macd_hist = macd_histogram.iloc[-1]
        
        current_atr = atr.iloc[-1]
        
        # Analyze market conditions
        trend_analysis = MarketAnalyzer.analyze_trend(df)
        volatility_analysis = MarketAnalyzer.analyze_volatility(df)
        
        # Initialize
        signal = "FLAT"
        rationale = []
        signal_strength = 0.5
        
        # EMA Crossover Logic
        ema_bullish = current_ema_fast > current_ema_slow
        ema_bearish = current_ema_fast < current_ema_slow
        ema_crossover_up = (prev_ema_fast <= prev_ema_slow) and (current_ema_fast > current_ema_slow)
        ema_crossover_down = (prev_ema_fast >= prev_ema_slow) and (current_ema_fast < current_ema_slow)
        
        # MACD Logic
        macd_bullish = current_macd > current_macd_signal
        macd_bearish = current_macd < current_macd_signal
        macd_crossover_up = (prev_macd <= prev_macd_signal) and (current_macd > current_macd_signal)
        macd_crossover_down = (prev_macd >= prev_macd_signal) and (current_macd < current_macd_signal)
        
        # Signal Generation
        if ema_bullish and macd_bullish:
            signal = "LONG"
            
            if ema_crossover_up:
                rationale.append(f"EMA golden cross: {self.ema_fast}/{self.ema_slow}")
                signal_strength += 0.25
            else:
                rationale.append(f"EMA{self.ema_fast} above EMA{self.ema_slow} (uptrend)")
                signal_strength += 0.15
            
            if macd_crossover_up:
                rationale.append("MACD bullish crossover")
                signal_strength += 0.2
            else:
                rationale.append("MACD above signal line")
                signal_strength += 0.1
            
            # MACD histogram strength
            if current_macd_hist > 0:
                macd_strength = min(abs(current_macd_hist) / abs(current_price) * 1000, 0.15)
                signal_strength += macd_strength
                rationale.append(f"MACD momentum positive")
        
        elif ema_bearish and macd_bearish:
            signal = "SHORT"
            
            if ema_crossover_down:
                rationale.append(f"EMA death cross: {self.ema_fast}/{self.ema_slow}")
                signal_strength += 0.25
            else:
                rationale.append(f"EMA{self.ema_fast} below EMA{self.ema_slow} (downtrend)")
                signal_strength += 0.15
            
            if macd_crossover_down:
                rationale.append("MACD bearish crossover")
                signal_strength += 0.2
            else:
                rationale.append("MACD below signal line")
                signal_strength += 0.1
            
            # MACD histogram strength
            if current_macd_hist < 0:
                macd_strength = min(abs(current_macd_hist) / abs(current_price) * 1000, 0.15)
                signal_strength += macd_strength
                rationale.append(f"MACD momentum negative")
        
        # Mixed signals - be cautious
        elif (ema_bullish and macd_bearish) or (ema_bearish and macd_bullish):
            signal = "FLAT"
            rationale.append("Mixed signals between EMA and MACD")
            rationale.append("Waiting for alignment")
        
        # Additional confirmation
        if signal != "FLAT":
            # Trend alignment
            if signal == "LONG" and trend_analysis["direction"] == "UP":
                signal_strength += 0.15
                rationale.append("Overall trend confirms bullish direction")
            elif signal == "SHORT" and trend_analysis["direction"] == "DOWN":
                signal_strength += 0.15
                rationale.append("Overall trend confirms bearish direction")
            elif signal != "FLAT":
                signal_strength -= 0.1
                rationale.append("Trend analysis shows mixed signals")
            
            # Price position relative to EMAs
            if signal == "LONG":
                if current_price > current_ema_fast > current_ema_slow:
                    signal_strength += 0.1
                    rationale.append("Price above both EMAs (strong uptrend)")
                elif current_price < current_ema_fast:
                    signal_strength -= 0.1
                    rationale.append("Price below fast EMA (potential weakness)")
            
            elif signal == "SHORT":
                if current_price < current_ema_fast < current_ema_slow:
                    signal_strength += 0.1
                    rationale.append("Price below both EMAs (strong downtrend)")
                elif current_price > current_ema_fast:
                    signal_strength -= 0.1
                    rationale.append("Price above fast EMA (potential weakness)")
            
            # Volatility check
            if volatility_analysis["level"] == "NORMAL":
                signal_strength += 0.1
                rationale.append("Normal volatility conditions")
            elif volatility_analysis["level"] == "HIGH":
                signal_strength -= 0.05
                rationale.append("Elevated volatility")
        
        # Calculate confidence
        market_conditions = {
            "volatility_factor": volatility_analysis["factor"],
            "trend_strength": trend_analysis["strength"]
        }
        
        confidence = SignalProcessor.calculate_confidence(signal_strength, market_conditions)
        
        # Calculate stop loss
        sl_pct = 0.025  # Default 2.5%
        tp_multiple = 1.5  # Standard trend following R/R
        
        if current_atr > 0 and current_price > 0:
            # Use 2.5x ATR as stop loss
            atr_sl_pct = (current_atr * 2.5) / current_price
            sl_pct = max(0.02, min(0.05, atr_sl_pct))  # Between 2% and 5%
            rationale.append(f"Stop loss set at 2.5*ATR: {sl_pct:.3f}")
        
        return SignalProcessor.format_signal_response(
            signal, confidence, sl_pct, tp_multiple, rationale
        )

# Initialize strategy
strategy = TrendStrategy()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "trend", "timestamp": pd.Timestamp.now().isoformat()}

@app.post("/signal")
async def get_signal(request: Dict):
    """
    Generate Trend trading signal
    
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
        "tp_multiple": 1.5,
        "rationale": ["explanation strings"]
    }
    """
    try:
        symbol = request.get("symbol")
        min_conf = request.get("min_conf", 0.5)
        
        if not symbol:
            raise HTTPException(status_code=400, detail="Symbol is required")
        
        logger.info(f"Generating Trend signal for {symbol}")
        
        # Fetch price data
        df = await strategy.data_fetcher.get_price_data(symbol, days_back=250)
        if df is None or len(df) < 200:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {symbol}")
        
        # Generate signal
        result = strategy.generate_signal(df)
        
        # Validate signal meets minimum confidence
        if not SignalProcessor.validate_signal(result["signal"], result["confidence"], min_conf):
            result["signal"] = "FLAT"
            result["rationale"].append(f"Signal confidence {result['confidence']} below minimum {min_conf}")
        
        logger.info(f"Trend signal for {symbol}: {result['signal']} (confidence: {result['confidence']})")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating Trend signal: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate signal: {str(e)}")

@app.get("/parameters")
async def get_parameters():
    """Get current strategy parameters"""
    return {
        "ema_fast": strategy.ema_fast,
        "ema_slow": strategy.ema_slow,
        "macd_fast": strategy.macd_fast,
        "macd_slow": strategy.macd_slow,
        "macd_signal": strategy.macd_signal,
        "description": "Trend following strategy using EMA crossovers and MACD confirmation"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

