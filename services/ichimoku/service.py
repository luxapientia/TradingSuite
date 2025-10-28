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

app = FastAPI(title="Ichimoku Strategy Service", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class IchimokuStrategy:
    """Ichimoku Kinko Hyo strategy implementation"""
    
    def __init__(self, monolith_url: str = "http://monolith:8000"):
        self.data_fetcher = PriceDataFetcher(monolith_url)
        self.tenkan_period = 9
        self.kijun_period = 26
        self.senkou_span_b_period = 52
        
    def calculate_ichimoku(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate Ichimoku Kinko Hyo components"""
        if len(df) < self.senkou_span_b_period:
            return df
        
        # Tenkan-sen (Conversion Line)
        tenkan_high = df["high"].rolling(window=self.tenkan_period).max()
        tenkan_low = df["low"].rolling(window=self.tenkan_period).min()
        df["tenkan_sen"] = (tenkan_high + tenkan_low) / 2
        
        # Kijun-sen (Base Line)
        kijun_high = df["high"].rolling(window=self.kijun_period).max()
        kijun_low = df["low"].rolling(window=self.kijun_period).min()
        df["kijun_sen"] = (kijun_high + kijun_low) / 2
        
        # Senkou Span A (Leading Span A)
        df["senkou_span_a"] = ((df["tenkan_sen"] + df["kijun_sen"]) / 2).shift(self.kijun_period)
        
        # Senkou Span B (Leading Span B)
        senkou_b_high = df["high"].rolling(window=self.senkou_span_b_period).max()
        senkou_b_low = df["low"].rolling(window=self.senkou_span_b_period).min()
        df["senkou_span_b"] = ((senkou_b_high + senkou_b_low) / 2).shift(self.kijun_period)
        
        # Chikou Span (Lagging Span)
        df["chikou_span"] = df["close"].shift(-self.kijun_period)
        
        # Cloud (Kumo)
        df["cloud_top"] = np.maximum(df["senkou_span_a"], df["senkou_span_b"])
        df["cloud_bottom"] = np.minimum(df["senkou_span_a"], df["senkou_span_b"])
        
        return df
    
    def analyze_ichimoku_signals(self, df: pd.DataFrame) -> Dict:
        """Analyze Ichimoku signals and market position"""
        if len(df) < self.kijun_period + 1:
            return {"signal": "FLAT", "confidence": 0.0, "analysis": {}}
        
        current_price = df["close"].iloc[-1]
        tenkan = df["tenkan_sen"].iloc[-1]
        kijun = df["kijun_sen"].iloc[-1]
        cloud_top = df["cloud_top"].iloc[-1]
        cloud_bottom = df["cloud_bottom"].iloc[-1]
        chikou = df["chikou_span"].iloc[-26] if len(df) >= 52 else None
        
        analysis = {
            "price_vs_cloud": "above" if current_price > cloud_top else "below" if current_price < cloud_bottom else "inside",
            "tenkan_vs_kijun": "above" if tenkan > kijun else "below",
            "price_vs_tenkan": "above" if current_price > tenkan else "below",
            "price_vs_kijun": "above" if current_price > kijun else "below",
            "cloud_color": "green" if df["senkou_span_a"].iloc[-1] > df["senkou_span_b"].iloc[-1] else "red",
            "chikou_position": "above" if chikou and chikou > df["close"].iloc[-26] else "below" if chikou else "unknown"
        }
        
        return analysis
    
    def generate_signal(self, df: pd.DataFrame) -> Dict:
        """Generate trading signal based on Ichimoku analysis"""
        if len(df) < self.kijun_period + 1:
            return {
                "signal": "FLAT",
                "confidence": 0.0,
                "sl_pct": 0.0,
                "tp_multiple": 0.0,
                "rationale": ["Insufficient data for Ichimoku analysis"]
            }
        
        # Analyze Ichimoku signals
        ichimoku_analysis = self.analyze_ichimoku_signals(df)
        
        # Analyze market conditions
        trend_analysis = MarketAnalyzer.analyze_trend(df)
        volatility_analysis = MarketAnalyzer.analyze_volatility(df)
        
        # Determine signal based on Ichimoku rules
        signal = "FLAT"
        rationale = []
        signal_strength = 0.0
        
        # Rule 1: Price position relative to cloud
        if ichimoku_analysis["price_vs_cloud"] == "above":
            if ichimoku_analysis["cloud_color"] == "green":
                signal_strength += 0.3
                rationale.append("Price above green cloud - bullish")
            else:
                signal_strength += 0.1
                rationale.append("Price above red cloud - weak bullish")
        elif ichimoku_analysis["price_vs_cloud"] == "below":
            if ichimoku_analysis["cloud_color"] == "red":
                signal_strength += 0.3
                rationale.append("Price below red cloud - bearish")
            else:
                signal_strength += 0.1
                rationale.append("Price below green cloud - weak bearish")
        else:
            rationale.append("Price inside cloud - neutral")
        
        # Rule 2: Tenkan vs Kijun relationship
        if ichimoku_analysis["tenkan_vs_kijun"] == "above":
            signal_strength += 0.2
            rationale.append("Tenkan above Kijun - bullish momentum")
        else:
            signal_strength += 0.2
            rationale.append("Tenkan below Kijun - bearish momentum")
        
        # Rule 3: Price vs Tenkan/Kijun
        if ichimoku_analysis["price_vs_tenkan"] == "above" and ichimoku_analysis["price_vs_kijun"] == "above":
            signal_strength += 0.2
            rationale.append("Price above both Tenkan and Kijun - strong bullish")
        elif ichimoku_analysis["price_vs_tenkan"] == "below" and ichimoku_analysis["price_vs_kijun"] == "below":
            signal_strength += 0.2
            rationale.append("Price below both Tenkan and Kijun - strong bearish")
        
        # Rule 4: Chikou Span confirmation
        if ichimoku_analysis["chikou_position"] == "above":
            signal_strength += 0.1
            rationale.append("Chikou Span confirms bullish trend")
        elif ichimoku_analysis["chikou_position"] == "below":
            signal_strength += 0.1
            rationale.append("Chikou Span confirms bearish trend")
        
        # Determine final signal
        if signal_strength >= 0.6:
            if ichimoku_analysis["price_vs_cloud"] in ["above"] and ichimoku_analysis["tenkan_vs_kijun"] == "above":
                signal = "LONG"
            elif ichimoku_analysis["price_vs_cloud"] in ["below"] and ichimoku_analysis["tenkan_vs_kijun"] == "below":
                signal = "SHORT"
            else:
                signal = "FLAT"
                rationale.append("Mixed signals - no clear direction")
        else:
            signal = "FLAT"
            rationale.append("Insufficient signal strength")
        
        # Adjust confidence based on market conditions
        if signal != "FLAT":
            if trend_analysis["strength"] > 0.6:
                signal_strength += 0.1
                rationale.append("Strong trend supports Ichimoku signal")
            
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
        sl_pct = 0.03  # Default 3% (Ichimoku signals are typically longer-term)
        tp_multiple = 2.0  # Default 2:1 R/R
        
        # Adjust based on cloud thickness
        cloud_thickness = abs(df["senkou_span_a"].iloc[-1] - df["senkou_span_b"].iloc[-1]) / df["close"].iloc[-1]
        if cloud_thickness > 0.05:  # Thick cloud
            sl_pct = max(0.025, min(0.05, cloud_thickness))
            rationale.append(f"Stop loss adjusted for thick cloud: {sl_pct:.3f}")
        
        return SignalProcessor.format_signal_response(
            signal, confidence, sl_pct, tp_multiple, rationale
        )

# Initialize strategy
strategy = IchimokuStrategy()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "ichimoku", "timestamp": pd.Timestamp.now().isoformat()}

@app.post("/signal")
async def get_signal(request: Dict):
    """
    Generate Ichimoku trading signal
    
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
        
        logger.info(f"Generating Ichimoku signal for {symbol}")
        
        # Fetch price data
        df = await strategy.data_fetcher.get_price_data(symbol)
        if df is None or len(df) < 100:
            raise HTTPException(status_code=404, detail=f"Insufficient data for {symbol}")
        
        # Calculate Ichimoku
        df = strategy.calculate_ichimoku(df)
        
        # Generate signal
        result = strategy.generate_signal(df)
        
        # Validate signal meets minimum confidence
        if not SignalProcessor.validate_signal(result["signal"], result["confidence"], min_conf):
            result["signal"] = "FLAT"
            result["rationale"].append(f"Signal confidence {result['confidence']} below minimum {min_conf}")
        
        logger.info(f"Ichimoku signal for {symbol}: {result['signal']} (confidence: {result['confidence']})")
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating Ichimoku signal: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate signal: {str(e)}")

@app.get("/parameters")
async def get_parameters():
    """Get current strategy parameters"""
    return {
        "tenkan_period": strategy.tenkan_period,
        "kijun_period": strategy.kijun_period,
        "senkou_span_b_period": strategy.senkou_span_b_period,
        "description": "Ichimoku Kinko Hyo strategy using cloud analysis and multiple timeframe confirmation"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
