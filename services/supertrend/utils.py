import httpx
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class PriceDataFetcher:
    """Utility class for fetching price data from the monolith service"""
    
    def __init__(self, monolith_url: str = "http://monolith:8000"):
        self.monolith_url = monolith_url
    
    async def get_price_data(self, symbol: str, days_back: int = 200) -> Optional[pd.DataFrame]:
        """
        Fetch price data for a symbol from the monolith service
        
        Args:
            symbol: Trading symbol (e.g., "XAUUSD=X")
            days_back: Number of days of historical data to fetch
            
        Returns:
            DataFrame with OHLC data or None if failed
        """
        try:
            start_date = (datetime.now() - timedelta(days=days_back)).strftime("%Y-%m-%d")
            
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.get(
                    f"{self.monolith_url}/prices",
                    params={"symbol": symbol, "start": start_date}
                )
                response.raise_for_status()
                data = response.json()
            
            # Convert to DataFrame
            df = pd.DataFrame(data["data"])
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
            df.sort_index(inplace=True)
            
            logger.info(f"Fetched {len(df)} records for {symbol}")
            return df
            
        except Exception as e:
            logger.error(f"Failed to fetch data for {symbol}: {e}")
            return None

class TechnicalIndicators:
    """Collection of technical indicators used across strategy services"""
    
    @staticmethod
    def sma(data: pd.Series, period: int) -> pd.Series:
        """Simple Moving Average"""
        return data.rolling(window=period).mean()
    
    @staticmethod
    def ema(data: pd.Series, period: int) -> pd.Series:
        """Exponential Moving Average"""
        return data.ewm(span=period).mean()
    
    @staticmethod
    def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Average True Range"""
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()
    
    @staticmethod
    def rsi(data: pd.Series, period: int = 14) -> pd.Series:
        """Relative Strength Index"""
        delta = data.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    @staticmethod
    def bollinger_bands(data: pd.Series, period: int = 20, std_dev: float = 2) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Bollinger Bands"""
        sma = TechnicalIndicators.sma(data, period)
        std = data.rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        return upper, sma, lower
    
    @staticmethod
    def macd(data: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """MACD (Moving Average Convergence Divergence)"""
        ema_fast = TechnicalIndicators.ema(data, fast)
        ema_slow = TechnicalIndicators.ema(data, slow)
        macd_line = ema_fast - ema_slow
        signal_line = TechnicalIndicators.ema(macd_line, signal)
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

class SignalProcessor:
    """Utility class for processing and validating trading signals"""
    
    @staticmethod
    def calculate_confidence(signal_strength: float, market_conditions: Dict) -> float:
        """
        Calculate confidence score based on signal strength and market conditions
        
        Args:
            signal_strength: Raw signal strength (0-1)
            market_conditions: Dictionary with market condition factors
            
        Returns:
            Confidence score (0-1)
        """
        base_confidence = signal_strength
        
        # Adjust based on market conditions
        volatility_factor = market_conditions.get("volatility_factor", 1.0)
        trend_strength = market_conditions.get("trend_strength", 0.5)
        
        # Higher trend strength increases confidence
        trend_adjustment = trend_strength * 0.2
        
        # High volatility decreases confidence
        volatility_adjustment = -(volatility_factor - 1.0) * 0.1
        
        confidence = base_confidence + trend_adjustment + volatility_adjustment
        
        # Ensure confidence is between 0 and 1
        return max(0.0, min(1.0, confidence))
    
    @staticmethod
    def validate_signal(signal: str, confidence: float, min_confidence: float = 0.5) -> bool:
        """Validate if a signal meets minimum requirements"""
        if signal not in ["LONG", "SHORT", "FLAT"]:
            return False
        
        if signal == "FLAT":
            return True
        
        return confidence >= min_confidence
    
    @staticmethod
    def format_signal_response(signal: str, confidence: float, sl_pct: float, 
                             tp_multiple: float, rationale: List[str]) -> Dict:
        """Format signal response in standard format"""
        return {
            "signal": signal,
            "confidence": round(confidence, 3),
            "sl_pct": sl_pct,
            "tp_multiple": tp_multiple,
            "rationale": rationale,
            "timestamp": datetime.now().isoformat()
        }

class MarketAnalyzer:
    """Utility class for analyzing market conditions"""
    
    @staticmethod
    def analyze_trend(df: pd.DataFrame, period: int = 20) -> Dict:
        """Analyze trend strength and direction"""
        if len(df) < period:
            return {"direction": "FLAT", "strength": 0.0}
        
        sma_short = TechnicalIndicators.sma(df["close"], period // 2)
        sma_long = TechnicalIndicators.sma(df["close"], period)
        
        current_price = df["close"].iloc[-1]
        sma_short_val = sma_short.iloc[-1]
        sma_long_val = sma_long.iloc[-1]
        
        # Determine trend direction
        if current_price > sma_short_val > sma_long_val:
            direction = "UP"
        elif current_price < sma_short_val < sma_long_val:
            direction = "DOWN"
        else:
            direction = "SIDEWAYS"
        
        # Calculate trend strength
        price_deviation = abs(current_price - sma_long_val) / sma_long_val
        strength = min(1.0, price_deviation * 10)  # Scale to 0-1
        
        return {
            "direction": direction,
            "strength": strength,
            "sma_short": sma_short_val,
            "sma_long": sma_long_val
        }
    
    @staticmethod
    def analyze_volatility(df: pd.DataFrame, period: int = 20) -> Dict:
        """Analyze market volatility"""
        if len(df) < period:
            return {"level": "UNKNOWN", "factor": 1.0}
        
        atr = TechnicalIndicators.atr(df["high"], df["low"], df["close"], period)
        current_atr = atr.iloc[-1]
        avg_atr = atr.mean()
        
        volatility_factor = current_atr / avg_atr if avg_atr > 0 else 1.0
        
        if volatility_factor > 1.5:
            level = "HIGH"
        elif volatility_factor < 0.7:
            level = "LOW"
        else:
            level = "NORMAL"
        
        return {
            "level": level,
            "factor": volatility_factor,
            "current_atr": current_atr,
            "avg_atr": avg_atr
        }
