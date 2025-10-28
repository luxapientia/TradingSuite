from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import numpy as np
import logging
from typing import Dict, List
import sys
import os

# Add the common utils to the path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'common'))

from utils import PriceDataFetcher, TechnicalIndicators, SignalProcessor, MarketAnalyzer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AlphaTrend Strategy Service", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AlphaTrendStrategy:
    """AlphaTrend strategy implementation - volatility adaptive trend following"""
    
    def __init__(self, monolith_url: str = "http://monolith:8000"):
        self.data_fetcher = PriceDataFetcher(monolith_url)
        self.atr_period = 14
        self.atr_multiplier = 2.0
        self.alpha_period = 21
        
    def calculate_alpha_trend(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate AlphaTrend indicator"""
        if len(df) < max(self.atr_period, self.alpha_period):
            return df
        
        # Calculate ATR
        atr = TechnicalIndicators.atr(df["high"], df["low"], df["close"], self.atr_period)
        
        # Calculate Alpha (volatility adaptive factor)
        alpha = 2.0 / (self.alpha_period + 1)
        
        # Calculate basic upper and lower bands
        hl2 = (df["high"] + df["low"]) / 2
        upper_band = hl2 + (self.atr_multiplier * atr)
        lower_band = hl2 - (self.atr_multiplier * atr)
        
        # Initialize arrays
        alpha_trend = pd.Series(index=df.index, dtype=float)
        direction = pd.Series(index=df.index, dtype=int)
        
        # Calculate AlphaTrend
        for i in range(len(df)):
            if i == 0:
                alpha_trend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1
            else:
                # Previous values
                prev_alpha_trend = alpha_trend.iloc[i-1]
                prev_direction = direction.iloc[i-1]
                
                # Current values
                current_upper = upper_band.iloc[i]
                current_lower = lower_band.iloc[i]
                current_close = df["close"].iloc[i]
                
                # Calculate new AlphaTrend with adaptive smoothing
                if prev_direction == 1:  # Previous trend was up
                    if current_close <= current_lower:
                        alpha_trend.iloc[i] = current_lower
                        direction.iloc[i] = -1
                    else:
                        # Apply alpha smoothing
                        alpha_trend.iloc[i] = alpha * min(current_upper, prev_alpha_trend) + (1 - alpha) * prev_alpha_trend
                        direction.iloc[i] = 1
                else:  # Previous trend was down
                    if current_close >= current_upper:
                        alpha_trend.iloc[i] = current_upper
                        direction.iloc[i] = 1
                    else:
                        # Apply alpha smoothing
                        alpha_trend.iloc[i] = alpha * max(current_lower, prev_alpha_trend) + (1 - alpha) * prev_alpha_trend
                        direction.iloc[i] = -1
        
        df["alpha_trend"] = alpha_trend
        df["alpha_trend_direction"] = direction
        df["atr"] = atr
        
        return df
    
    def generate_signal(self, df: pd.DataFrame) -> Dict:
        """Generate trading signal based on AlphaTrend"""
        if len(df) < 2:
            return {
                "signal": "FLAT",
                "confidence": 0.0,
                "sl_pct": 0.0,
                "tp_multiple": 0.0,
                "rationale": ["Insufficient data for signal generation"]
            }
        
        # Get current and previous values
        current_direction = df["alpha_trend_direction"].iloc[-1]
        prev_direction = df["alpha_trend_direction"].iloc[-2]
        current_price = df["close"].iloc[-1]
        current_alpha_trend = df["alpha_trend"].iloc[-1]
        current_atr = df["atr"].iloc[-1]
        
        # Analyze market conditions
        trend_analysis = MarketAnalyzer.analyze_trend(df)
        volatility_analysis = MarketAnalyzer.analyze_volatility(df)
        
        # Determine signal
        signal = "FLAT"
        rationale = []
        
        if current_direction == 1 and prev_direction == -1:
            # Trend changed from down to up
            signal = "LONG"
            rationale.append("AlphaTrend changed from bearish to bullish")
        elif current_direction == -1 and prev_direction == 1:
            # Trend changed from up to down
            signal = "SHORT"
            rationale.append("AlphaTrend changed from bullish to bearish")
        elif current_direction == 1:
            # Still in uptrend
            signal = "LONG"
            rationale.append("AlphaTrend remains bullish")
        elif current_direction == -1:
            # Still in downtrend
            signal = "SHORT"
            rationale.append("AlphaTrend remains bearish")
        
        # Calculate confidence based on signal strength and market conditions
        signal_strength = 0.6  # Base strength (higher than Supertrend due to smoothing)
        
        # Adjust based on trend alignment
        if signal == "LONG" and trend_analysis["direction"] == "UP":
            signal_strength += 0.2
            rationale.append("Trend analysis confirms bullish direction")
        elif signal == "SHORT" and trend_analysis["direction"] == "DOWN":
            signal_strength += 0.2
            rationale.append("Trend analysis confirms bearish direction")
        elif signal != "FLAT":
            signal_strength -= 0.1
            rationale.append("Trend analysis conflicts with AlphaTrend signal")
        
        # Adjust based on volatility (AlphaTrend performs better in trending markets)
        if volatility_analysis["level"] == "NORMAL" and trend_analysis["strength"] > 0.6:
            signal_strength += 0.15
            rationale.append("Strong trend with normal volatility - optimal conditions")
        elif volatility_analysis["level"] == "HIGH":
            signal_strength -= 0.05
            rationale.append("High volatility reduces signal reliability")
        elif trend_analysis["strength"] < 0.3:
            signal_strength -= 0.1
            rationale.append("Weak trend reduces signal strength")
        
        # Calculate confidence
        market_conditions = {
            "volatility_factor": volatility_analysis["factor"],
            "trend_strength": trend_analysis["strength"]
        }
        
        confidence = SignalProcessor.calculate_confidence(signal_strength, market_conditions)
        
        # Calculate stop loss and take profit
        sl_pct = 0.025  # Default 2.5%
        tp_multiple = 1.5  # Default 1.5:1 R/R
        
        if current_atr > 0:
            # Adjust SL based on ATR (more conservative than Supertrend)
            atr_sl_pct = (current_atr * 1.5) / current_price
            sl_pct = max(0.015, min(0.04, atr_sl_pct))  # Between 1.5% and 4%
            rationale.append(f"Stop loss adjusted based on ATR: {sl_pct:.3f}")
        
        return SignalProcessor.format_signal_response(
            signal, confidence, sl_pct, tp_multiple, rationale
        )

# Initialize strategy
strategy = AlphaTrendStrategy()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "alphatrend", "timestamp": pd.Timestamp.now().isoformat()}

@app.post("/signal")
async def get_signal(request: Dict):
    """
    Generate AlphaTrend trading signal
    
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
        
        logger.info(f"Generating AlphaTrend signal for {symbol}")
        
        # Fetch price data
        df = await strategy.data_fetcher.get_price_data(symbol)
        if df is None or len(df) < 50:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {symbol}")
        
        # Calculate AlphaTrend
        df = strategy.calculate_alpha_trend(df)
        
        # Generate signal
        result = strategy.generate_signal(df)
        
        # Validate signal meets minimum confidence
        if not SignalProcessor.validate_signal(result["signal"], result["confidence"], min_conf):
            result["signal"] = "FLAT"
            result["rationale"].append(f"Signal confidence {result['confidence']} below minimum {min_conf}")
        
        logger.info(f"AlphaTrend signal for {symbol}: {result['signal']} (confidence: {result['confidence']})")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating AlphaTrend signal: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate signal: {str(e)}")

@app.get("/parameters")
async def get_parameters():
    """Get current strategy parameters"""
    return {
        "atr_period": strategy.atr_period,
        "atr_multiplier": strategy.atr_multiplier,
        "alpha_period": strategy.alpha_period,
        "description": "AlphaTrend strategy using volatility adaptive trend following with exponential smoothing"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
