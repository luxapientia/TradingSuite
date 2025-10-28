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

app = FastAPI(title="QQE-SSL-WAE Strategy Service", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class QQESSLWAEStrategy:
    """QQE-SSL-WAE composite strategy implementation"""
    
    def __init__(self, monolith_url: str = "http://monolith:8000"):
        self.data_fetcher = PriceDataFetcher(monolith_url)
        self.qqe_period = 14
        self.ssl_period = 10
        self.wae_period = 20
        
    def calculate_qqe(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate QQE (Quantitative Qualitative Estimation) indicator"""
        if len(df) < self.qqe_period * 2:
            return df
        
        # Calculate RSI
        rsi = TechnicalIndicators.rsi(df["close"], self.qqe_period)
        
        # Calculate QQE
        qqe_factor = 4.236
        qqe_period = 5
        
        # Smooth RSI
        rsi_smooth = rsi.ewm(span=qqe_period).mean()
        
        # Calculate QQE line
        qqe_line = rsi_smooth.ewm(span=qqe_period).mean()
        
        # Calculate QQE signal line
        qqe_signal = qqe_line.ewm(span=qqe_period).mean()
        
        df["qqe_line"] = qqe_line
        df["qqe_signal"] = qqe_signal
        df["qqe_rsi"] = rsi_smooth
        
        return df
    
    def calculate_ssl(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate SSL (SSL Channel) indicator"""
        if len(df) < self.ssl_period * 2:
            return df
        
        # Calculate SSL upper and lower bands
        ssl_high = df["high"].rolling(window=self.ssl_period).max()
        ssl_low = df["low"].rolling(window=self.ssl_period).min()
        
        # SSL Channel
        ssl_up = (ssl_high + ssl_low) / 2
        ssl_down = ssl_up
        
        # SSL direction
        ssl_direction = pd.Series(index=df.index, dtype=int)
        ssl_direction.iloc[0] = 1
        
        for i in range(1, len(df)):
            if df["close"].iloc[i] > ssl_up.iloc[i-1]:
                ssl_direction.iloc[i] = 1
            elif df["close"].iloc[i] < ssl_down.iloc[i-1]:
                ssl_direction.iloc[i] = -1
            else:
                ssl_direction.iloc[i] = ssl_direction.iloc[i-1]
        
        df["ssl_up"] = ssl_up
        df["ssl_down"] = ssl_down
        df["ssl_direction"] = ssl_direction
        
        return df
    
    def calculate_wae(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate WAE (Williams Accumulation/Distribution) indicator"""
        if len(df) < self.wae_period:
            return df
        
        # Calculate Williams Accumulation/Distribution
        wae = pd.Series(index=df.index, dtype=float)
        
        for i in range(len(df)):
            if i == 0:
                wae.iloc[i] = 0
            else:
                # True Range
                tr = max(
                    df["high"].iloc[i] - df["low"].iloc[i],
                    abs(df["high"].iloc[i] - df["close"].iloc[i-1]),
                    abs(df["low"].iloc[i] - df["close"].iloc[i-1])
                )
                
                # Williams A/D
                if tr > 0:
                    wae.iloc[i] = wae.iloc[i-1] + ((df["close"].iloc[i] - df["low"].iloc[i]) - (df["high"].iloc[i] - df["close"].iloc[i])) / tr
                else:
                    wae.iloc[i] = wae.iloc[i-1]
        
        # Smooth WAE
        df["wae"] = wae.ewm(span=self.wae_period).mean()
        
        return df
    
    def analyze_composite_signals(self, df: pd.DataFrame) -> Dict:
        """Analyze QQE, SSL, and WAE signals"""
        if len(df) < max(self.qqe_period, self.ssl_period, self.wae_period) + 1:
            return {"signals": {}, "consensus": "FLAT"}
        
        current_price = df["close"].iloc[-1]
        prev_price = df["close"].iloc[-2]
        
        signals = {}
        
        # QQE Analysis
        qqe_line = df["qqe_line"].iloc[-1]
        qqe_signal = df["qqe_signal"].iloc[-1]
        qqe_rsi = df["qqe_rsi"].iloc[-1]
        
        if qqe_line > qqe_signal and qqe_rsi > 50:
            signals["qqe"] = "LONG"
        elif qqe_line < qqe_signal and qqe_rsi < 50:
            signals["qqe"] = "SHORT"
        else:
            signals["qqe"] = "FLAT"
        
        # SSL Analysis
        ssl_direction = df["ssl_direction"].iloc[-1]
        ssl_up = df["ssl_up"].iloc[-1]
        ssl_down = df["ssl_down"].iloc[-1]
        
        if ssl_direction == 1 and current_price > ssl_up:
            signals["ssl"] = "LONG"
        elif ssl_direction == -1 and current_price < ssl_down:
            signals["ssl"] = "SHORT"
        else:
            signals["ssl"] = "FLAT"
        
        # WAE Analysis
        wae_current = df["wae"].iloc[-1]
        wae_prev = df["wae"].iloc[-2]
        
        if wae_current > wae_prev and wae_current > 0:
            signals["wae"] = "LONG"
        elif wae_current < wae_prev and wae_current < 0:
            signals["wae"] = "SHORT"
        else:
            signals["wae"] = "FLAT"
        
        # Determine consensus (need at least 2 out of 3 signals to agree)
        long_count = sum(1 for s in signals.values() if s == "LONG")
        short_count = sum(1 for s in signals.values() if s == "SHORT")
        
        if long_count >= 2:
            consensus = "LONG"
        elif short_count >= 2:
            consensus = "SHORT"
        else:
            consensus = "FLAT"
        
        return {
            "signals": signals,
            "consensus": consensus,
            "long_count": long_count,
            "short_count": short_count
        }
    
    def generate_signal(self, df: pd.DataFrame) -> Dict:
        """Generate trading signal based on QQE-SSL-WAE composite analysis"""
        if len(df) < max(self.qqe_period, self.ssl_period, self.wae_period) + 1:
            return {
                "signal": "FLAT",
                "confidence": 0.0,
                "sl_pct": 0.0,
                "tp_multiple": 0.0,
                "rationale": ["Insufficient data for composite analysis"]
            }
        
        # Calculate all indicators
        df = self.calculate_qqe(df)
        df = self.calculate_ssl(df)
        df = self.calculate_wae(df)
        
        # Analyze composite signals
        composite_analysis = self.analyze_composite_signals(df)
        
        # Analyze market conditions
        trend_analysis = MarketAnalyzer.analyze_trend(df)
        volatility_analysis = MarketAnalyzer.analyze_volatility(df)
        
        # Determine signal
        signal = composite_analysis["consensus"]
        rationale = []
        signal_strength = 0.0
        
        # Base strength based on consensus
        if signal == "LONG":
            signal_strength = 0.4 + (composite_analysis["long_count"] * 0.2)
            rationale.append(f"QQE-SSL-WAE consensus: {composite_analysis['long_count']}/3 indicators bullish")
        elif signal == "SHORT":
            signal_strength = 0.4 + (composite_analysis["short_count"] * 0.2)
            rationale.append(f"QQE-SSL-WAE consensus: {composite_analysis['short_count']}/3 indicators bearish")
        else:
            rationale.append("QQE-SSL-WAE consensus: No clear direction")
        
        # Add individual signal details
        for indicator, sig in composite_analysis["signals"].items():
            rationale.append(f"{indicator.upper()}: {sig}")
        
        # Adjust based on market conditions
        if signal != "FLAT":
            if trend_analysis["strength"] > 0.6:
                signal_strength += 0.1
                rationale.append("Strong trend supports composite signal")
            
            if volatility_analysis["level"] == "NORMAL":
                signal_strength += 0.05
                rationale.append("Normal volatility conditions")
            elif volatility_analysis["level"] == "HIGH":
                signal_strength -= 0.05
                rationale.append("High volatility reduces reliability")
        
        # Calculate confidence
        market_conditions = {
            "volatility_factor": volatility_analysis["factor"],
            "trend_strength": trend_analysis["strength"]
        }
        
        confidence = SignalProcessor.calculate_confidence(signal_strength, market_conditions)
        
        # Calculate stop loss and take profit
        sl_pct = 0.025  # Default 2.5%
        tp_multiple = 1.5  # Default 1.5:1 R/R
        
        # Adjust based on volatility
        if volatility_analysis["factor"] > 1.2:
            sl_pct = min(0.04, sl_pct * volatility_analysis["factor"])
            rationale.append(f"Stop loss adjusted for high volatility: {sl_pct:.3f}")
        
        return SignalProcessor.format_signal_response(
            signal, confidence, sl_pct, tp_multiple, rationale
        )

# Initialize strategy
strategy = QQESSLWAEStrategy()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "qqe_ssl_wae", "timestamp": pd.Timestamp.now().isoformat()}

@app.post("/signal")
async def get_signal(request: Dict):
    """
    Generate QQE-SSL-WAE composite trading signal
    
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
        
        logger.info(f"Generating QQE-SSL-WAE signal for {symbol}")
        
        # Fetch price data
        df = await strategy.data_fetcher.get_price_data(symbol)
        if df is None or len(df) < 100:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {symbol}")
        
        # Generate signal
        result = strategy.generate_signal(df)
        
        # Validate signal meets minimum confidence
        if not SignalProcessor.validate_signal(result["signal"], result["confidence"], min_conf):
            result["signal"] = "FLAT"
            result["rationale"].append(f"Signal confidence {result['confidence']} below minimum {min_conf}")
        
        logger.info(f"QQE-SSL-WAE signal for {symbol}: {result['signal']} (confidence: {result['confidence']})")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating QQE-SSL-WAE signal: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate signal: {str(e)}")

@app.get("/parameters")
async def get_parameters():
    """Get current strategy parameters"""
    return {
        "qqe_period": strategy.qqe_period,
        "ssl_period": strategy.ssl_period,
        "wae_period": strategy.wae_period,
        "description": "QQE-SSL-WAE composite strategy requiring 2/3 indicators to agree for signal generation"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
