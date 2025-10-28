from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import asyncio
from typing import Dict, List, Optional
import logging
from datetime import datetime
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Trading Suite Orchestrator", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Service URLs
SERVICE_URLS = {
    "supertrend": "http://supertrend:8000",
    "alphatrend": "http://alphatrend:8000", 
    "ichimoku": "http://ichimoku:8000",
    "qqe_ssl_wae": "http://qqe_ssl_wae:8000",
    "turtle": "http://turtle:8000",
    "meanrev": "http://meanrev:8000",
    "trend": "http://trend:8000"
}

class TradingOrchestrator:
    def __init__(self):
        self.min_confidence = 0.7
        self.min_holding_days = 7
        self.default_sl_pct = 0.025
        self.default_tp_multiple = 1.5
        
    async def get_signal_from_service(self, service_name: str, symbol: str, min_conf: float) -> Dict:
        """Get signal from a specific strategy service"""
        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                response = await client.post(
                    f"{SERVICE_URLS[service_name]}/signal",
                    json={"symbol": symbol, "min_conf": min_conf}
                )
                response.raise_for_status()
                return response.json()
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}" if e.response.text else f"HTTP {e.response.status_code}"
            logger.error(f"HTTP error getting signal from {service_name}: {error_msg}")
            return {
                "signal": "FLAT",
                "confidence": 0.0,
                "sl_pct": 0.0,
                "tp_multiple": 0.0,
                "rationale": [f"Service HTTP error: {error_msg}"]
            }
        except Exception as e:
            error_msg = str(e) if str(e) else f"Unknown error: {type(e).__name__}"
            logger.error(f"Error getting signal from {service_name}: {error_msg}")
            return {
                "signal": "FLAT",
                "confidence": 0.0,
                "sl_pct": 0.0,
                "tp_multiple": 0.0,
                "rationale": [f"Service error: {error_msg}"]
            }
    
    async def aggregate_signals(self, symbol: str, min_conf: float) -> Dict:
        """Aggregate signals from all strategy services"""
        # Get signals from all services concurrently
        tasks = [
            self.get_signal_from_service(service, symbol, min_conf)
            for service in SERVICE_URLS.keys()
        ]
        
        results = await asyncio.gather(*tasks)
        
        # Process results
        components = []
        long_signals = 0
        short_signals = 0
        total_confidence = 0.0
        valid_signals = 0
        
        for i, (service_name, result) in enumerate(zip(SERVICE_URLS.keys(), results)):
            components.append({
                "svc": service_name,
                "signal": result["signal"],
                "confidence": result["confidence"],
                "rationale": result["rationale"]
            })
            
            if result["signal"] != "FLAT":
                valid_signals += 1
                total_confidence += result["confidence"]
                
                if result["signal"] == "LONG":
                    long_signals += 1
                elif result["signal"] == "SHORT":
                    short_signals += 1
        
        # Calculate final decision
        if valid_signals == 0:
            decision = "FLAT"
            confidence = 0.0
        else:
            avg_confidence = total_confidence / valid_signals
            
            # Apply confidence gating
            if avg_confidence < min_conf:
                decision = "FLAT"
                confidence = avg_confidence
            else:
                # Determine direction based on majority
                if long_signals > short_signals:
                    decision = "LONG"
                elif short_signals > long_signals:
                    decision = "SHORT"
                else:
                    decision = "FLAT"
                
                confidence = avg_confidence
        
        return {
            "decision": decision,
            "confidence": round(confidence, 3),
            "components": components,
            "sl_pct": self.default_sl_pct,
            "tp_multiple": self.default_tp_multiple,
            "metadata": {
                "total_signals": len(SERVICE_URLS),
                "valid_signals": valid_signals,
                "long_signals": long_signals,
                "short_signals": short_signals,
                "min_confidence_threshold": min_conf,
                "timestamp": datetime.now().isoformat()
            }
        }

# Initialize orchestrator
orchestrator = TradingOrchestrator()

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "orchestrator", "timestamp": datetime.now().isoformat()}

@app.post("/decide")
async def make_decision(request: Dict):
    """
    Make trading decision based on aggregated signals from all strategy services.
    
    Input:
    {
        "symbol": "XAUUSD=X",
        "min_conf": 0.7
    }
    
    Output:
    {
        "decision": "LONG|SHORT|FLAT",
        "confidence": 0.82,
        "components": [...],
        "sl_pct": 0.025,
        "tp_multiple": 1.5
    }
    """
    try:
        symbol = request.get("symbol")
        min_conf = request.get("min_conf", 0.7)
        
        if not symbol:
            raise HTTPException(status_code=400, detail="Symbol is required")
        
        logger.info(f"Making decision for {symbol} with min confidence {min_conf}")
        
        result = await orchestrator.aggregate_signals(symbol, min_conf)
        
        logger.info(f"Decision for {symbol}: {result['decision']} (confidence: {result['confidence']})")
        
        return result
        
    except Exception as e:
        logger.error(f"Error making decision: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to make decision: {str(e)}")

@app.get("/services/status")
async def check_services_status():
    """Check the health status of all strategy services"""
    status = {}
    
    for service_name, url in SERVICE_URLS.items():
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{url}/health")
                status[service_name] = {
                    "status": "healthy",
                    "response": response.json()
                }
        except Exception as e:
            status[service_name] = {
                "status": "unhealthy",
                "error": str(e)
            }
    
    return {
        "timestamp": datetime.now().isoformat(),
        "services": status
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8200)
