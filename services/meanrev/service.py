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

app = FastAPI(title="Mean Reversion Strategy Service", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class MeanReversionStrategy:
    """Mean reversion strategy using RSI and Bollinger Bands with ADX gate"""
    
    def __init__(self, monolith_url: str = "http://monolith:8000"):
        self.data_fetcher = PriceDataFetcher(monolith_url)
        self.rsi_period = 14
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        self.bb_period = 20
        self.bb_std = 2.0
        self.adx_period = 14
        self.adx_threshold = 25  # Only trade when ADX < 25 (weak trend)
        
    def calculate_zscore(self, data: pd.Series, period: int = 20) -> pd.Series:
        """Calculate z-score for Bollinger Band analysis"""
        mean = data.rolling(window=period).mean()
        std = data.rolling(window=period).std()
        return (data - mean) / std
    
    def calculate_adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate ADX (Average Directional Index)"""
        high = df['high']
        low = df['low']
        close = df['close']
        
        # Calculate +DM and -DM
        up_move = high.diff()
        down_move = -low.diff()
        
        plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
        minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
        
        # Calculate TR (True Range)
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Smooth TR, +DM, -DM using Wilder's smoothing
        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (pd.Series(plus_dm).rolling(window=period).mean() / atr)
        minus_di = 100 * (pd.Series(minus_dm).rolling(window=period).mean() / atr)
        
        # Calculate DX and ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        
        return adx
    
    def generate_signal(self, df: pd.DataFrame) -> Dict:
        """Generate trading signal based on mean reversion indicators"""
        if len(df) < max(self.rsi_period, self.bb_period, self.adx_period) + 1:
            return {
                "signal": "FLAT",
                "confidence": 0.0,
                "sl_pct": 0.0,
                "tp_multiple": 0.0,
                "rationale": ["Insufficient data for signal generation"]
            }
        
        # Calculate indicators
        close = df['close']
        rsi = TechnicalIndicators.rsi(close, self.rsi_period)
        bb_upper, bb_middle, bb_lower = TechnicalIndicators.bollinger_bands(
            close, self.bb_period, self.bb_std
        )
        zscore = self.calculate_zscore(close, self.bb_period)
        adx = self.calculate_adx(df, self.adx_period)
        atr = TechnicalIndicators.atr(df['high'], df['low'], df['close'], 14)
        
        # Get current values
        current_price = close.iloc[-1]
        current_rsi = rsi.iloc[-1]
        current_zscore = zscore.iloc[-1]
        current_adx = adx.iloc[-1]
        current_atr = atr.iloc[-1]
        current_bb_upper = bb_upper.iloc[-1]
        current_bb_lower = bb_lower.iloc[-1]
        
        # Analyze market conditions
        trend_analysis = MarketAnalyzer.analyze_trend(df)
        volatility_analysis = MarketAnalyzer.analyze_volatility(df)
        
        # Initialize
        signal = "FLAT"
        rationale = []
        signal_strength = 0.5
        
        # ADX Gate: Only trade in low-trend conditions (mean reversion works best)
        if pd.notna(current_adx) and current_adx > self.adx_threshold:
            return {
                "signal": "FLAT",
                "confidence": 0.0,
                "sl_pct": 0.0,
                "tp_multiple": 0.0,
                "rationale": [f"ADX too high ({current_adx:.1f} > {self.adx_threshold})",
                             "Trend too strong for mean reversion"]
            }
        
        # Mean Reversion Logic
        if pd.notna(current_rsi) and pd.notna(current_zscore):
            # Oversold conditions - potential LONG
            if current_rsi < self.rsi_oversold and current_zscore < -1.0:
                signal = "LONG"
                rationale.append(f"RSI oversold: {current_rsi:.1f} < {self.rsi_oversold}")
                rationale.append(f"Price below BB lower band (z={current_zscore:.2f})")
                rationale.append("Mean reversion setup detected")
                
                # Stronger signal if very extreme
                if current_rsi < 25 or current_zscore < -2.0:
                    signal_strength += 0.25
                    rationale.append("Extremely oversold conditions")
                else:
                    signal_strength += 0.15
                
            # Overbought conditions - potential SHORT
            elif current_rsi > self.rsi_overbought and current_zscore > 1.0:
                signal = "SHORT"
                rationale.append(f"RSI overbought: {current_rsi:.1f} > {self.rsi_overbought}")
                rationale.append(f"Price above BB upper band (z={current_zscore:.2f})")
                rationale.append("Mean reversion setup detected")
                
                # Stronger signal if very extreme
                if current_rsi > 75 or current_zscore > 2.0:
                    signal_strength += 0.25
                    rationale.append("Extremely overbought conditions")
                else:
                    signal_strength += 0.15
        
        # Additional confirmation checks
        if signal != "FLAT":
            # Confirm with ADX (lower is better for mean reversion)
            if pd.notna(current_adx):
                if current_adx < 20:
                    signal_strength += 0.15
                    rationale.append(f"ADX confirms weak trend: {current_adx:.1f}")
                else:
                    signal_strength += 0.05
                    rationale.append(f"ADX acceptable: {current_adx:.1f}")
            
            # Check volatility
            if volatility_analysis["level"] == "NORMAL":
                signal_strength += 0.1
                rationale.append("Normal volatility favors mean reversion")
            elif volatility_analysis["level"] == "LOW":
                signal_strength += 0.05
                rationale.append("Low volatility conditions")
            else:
                signal_strength -= 0.1
                rationale.append("High volatility reduces reliability")
            
            # Distance from mean (BB middle) as confidence factor
            distance_from_mean = abs((current_price - bb_middle.iloc[-1]) / bb_middle.iloc[-1])
            if distance_from_mean > 0.02:  # More than 2% from mean
                signal_strength += 0.1
                rationale.append(f"Good distance from mean: {distance_from_mean:.1%}")
        
        # Calculate confidence
        market_conditions = {
            "volatility_factor": volatility_analysis["factor"],
            "trend_strength": max(0, 1 - (current_adx / 50)) if pd.notna(current_adx) else 0.5
        }
        
        confidence = SignalProcessor.calculate_confidence(signal_strength, market_conditions)
        
        # Calculate stop loss (tighter for mean reversion)
        sl_pct = 0.018  # Default 1.8%
        tp_multiple = 1.2  # Mean reversion typically has lower R/R
        
        if current_atr > 0 and current_price > 0:
            # Use 1.8x ATR as stop loss (tighter than trend following)
            atr_sl_pct = (current_atr * 1.8) / current_price
            sl_pct = max(0.015, min(0.04, atr_sl_pct))  # Between 1.5% and 4%
            rationale.append(f"Stop loss set at 1.8*ATR: {sl_pct:.3f}")
        
        return SignalProcessor.format_signal_response(
            signal, confidence, sl_pct, tp_multiple, rationale
        )

# Initialize strategy
strategy = MeanReversionStrategy()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "meanrev", "timestamp": pd.Timestamp.now().isoformat()}

@app.post("/signal")
async def get_signal(request: Dict):
    """
    Generate Mean Reversion trading signal
    
    Input:
    {
        "symbol": "XAUUSD=X",
        "min_conf": 0.7
    }
    
    Output:
    {
        "signal": "LONG|SHORT|FLAT",
        "confidence": 0.82,
        "sl_pct": 0.018,
        "tp_multiple": 1.2,
        "rationale": ["explanation strings"]
    }
    """
    try:
        symbol = request.get("symbol")
        min_conf = request.get("min_conf", 0.5)
        
        if not symbol:
            raise HTTPException(status_code=400, detail="Symbol is required")
        
        logger.info(f"Generating Mean Reversion signal for {symbol}")
        
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
        
        logger.info(f"Mean Reversion signal for {symbol}: {result['signal']} (confidence: {result['confidence']})")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating Mean Reversion signal: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate signal: {str(e)}")

@app.get("/parameters")
async def get_parameters():
    """Get current strategy parameters"""
    return {
        "rsi_period": strategy.rsi_period,
        "rsi_oversold": strategy.rsi_oversold,
        "rsi_overbought": strategy.rsi_overbought,
        "bb_period": strategy.bb_period,
        "bb_std": strategy.bb_std,
        "adx_period": strategy.adx_period,
        "adx_threshold": strategy.adx_threshold,
        "description": "Mean reversion strategy using RSI, Bollinger Bands, and ADX gate"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

