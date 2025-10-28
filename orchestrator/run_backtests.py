import pandas as pd
import numpy as np
import httpx
import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BacktestRunner:
    """Walk-forward backtesting system for trading strategies"""
    
    def __init__(self, orchestrator_url: str = "http://localhost:8200", 
                 monolith_url: str = "http://localhost:8000"):
        self.orchestrator_url = orchestrator_url
        self.monolith_url = monolith_url
        self.output_dir = Path("outputs")
        self.output_dir.mkdir(exist_ok=True)
        
        # Backtest parameters
        self.min_confidence = 0.7
        self.min_holding_days = 7
        self.initial_capital = 100000
        self.commission_rate = 0.001  # 0.1%
        
    async def fetch_price_data(self, symbol: str, start_date: str, end_date: str) -> Optional[pd.DataFrame]:
        """Fetch price data from monolith service"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.monolith_url}/prices",
                    params={"symbol": symbol, "start": start_date, "end": end_date}
                )
                response.raise_for_status()
                data = response.json()
            
            df = pd.DataFrame(data["data"])
            df["date"] = pd.to_datetime(df["date"])
            df.set_index("date", inplace=True)
            df.sort_index(inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to fetch data for {symbol}: {e}")
            return None
    
    async def get_trading_signal(self, symbol: str, date: str) -> Dict:
        """Get trading signal from orchestrator"""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{self.orchestrator_url}/decide",
                    json={"symbol": symbol, "min_conf": self.min_confidence}
                )
                response.raise_for_status()
                return response.json()
                
        except Exception as e:
            logger.error(f"Failed to get signal for {symbol} on {date}: {e}")
            return {"decision": "FLAT", "confidence": 0.0}
    
    def calculate_position_size(self, signal: Dict, current_price: float, available_capital: float) -> float:
        """Calculate position size based on signal and available capital"""
        if signal["decision"] == "FLAT":
            return 0.0
        
        # Risk 2% of capital per trade
        risk_amount = available_capital * 0.02
        sl_pct = signal.get("sl_pct", 0.025)
        
        # Calculate position size based on stop loss
        position_size = risk_amount / (current_price * sl_pct)
        
        # Ensure we don't exceed available capital
        max_position_value = available_capital * 0.95  # Leave 5% buffer
        max_position_size = max_position_value / current_price
        
        return min(position_size, max_position_size)
    
    def calculate_trade_metrics(self, trades: List[Dict]) -> Dict:
        """Calculate comprehensive trading metrics"""
        if not trades:
            return {
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "total_return": 0.0
            }
        
        df_trades = pd.DataFrame(trades)
        
        # Basic metrics
        total_trades = len(trades)
        winning_trades = len(df_trades[df_trades["pnl"] > 0])
        losing_trades = len(df_trades[df_trades["pnl"] < 0])
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # P&L metrics
        total_pnl = df_trades["pnl"].sum()
        avg_win = df_trades[df_trades["pnl"] > 0]["pnl"].mean() if winning_trades > 0 else 0
        avg_loss = df_trades[df_trades["pnl"] < 0]["pnl"].mean() if losing_trades > 0 else 0
        
        # Profit factor
        gross_profit = df_trades[df_trades["pnl"] > 0]["pnl"].sum()
        gross_loss = abs(df_trades[df_trades["pnl"] < 0]["pnl"].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Calculate equity curve
        equity_curve = [self.initial_capital]
        for trade in trades:
            equity_curve.append(equity_curve[-1] + trade["pnl"])
        
        # Sharpe ratio (annualized)
        if len(equity_curve) > 1:
            returns = pd.Series(equity_curve).pct_change().dropna()
            if len(returns) > 0 and returns.std() > 0:
                sharpe_ratio = (returns.mean() * 252) / (returns.std() * np.sqrt(252))
            else:
                sharpe_ratio = 0.0
        else:
            sharpe_ratio = 0.0
        
        # Maximum drawdown
        equity_series = pd.Series(equity_curve)
        rolling_max = equity_series.expanding().max()
        drawdown = (equity_series - rolling_max) / rolling_max
        max_drawdown = drawdown.min()
        
        # Total return
        total_return = (equity_curve[-1] - self.initial_capital) / self.initial_capital
        
        return {
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 3),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 3),
            "sharpe_ratio": round(sharpe_ratio, 3),
            "max_drawdown": round(max_drawdown, 3),
            "total_return": round(total_return, 3),
            "final_capital": equity_curve[-1]
        }
    
    async def run_walk_forward_backtest(self, symbol: str, start_date: str, end_date: str, 
                                     window_size: int = 252, step_size: int = 21) -> Dict:
        """Run walk-forward backtest for a single symbol"""
        logger.info(f"Starting walk-forward backtest for {symbol}")
        
        # Fetch all price data
        df = await self.fetch_price_data(symbol, start_date, end_date)
        if df is None or len(df) < window_size:
            logger.error(f"Insufficient data for {symbol}")
            return {"error": "Insufficient data"}
        
        # Initialize tracking variables
        trades = []
        current_position = None
        capital = self.initial_capital
        equity_curve = [self.initial_capital]
        
        # Walk-forward testing
        start_idx = window_size
        for i in range(start_idx, len(df), step_size):
            current_date = df.index[i]
            
            # Get price data for current window
            window_start = df.index[i - window_size]
            window_end = current_date
            
            logger.info(f"Processing {symbol} on {current_date.strftime('%Y-%m-%d')}")
            
            # Get trading signal
            signal = await self.get_trading_signal(symbol, current_date.strftime('%Y-%m-%d'))
            current_price = df.loc[current_date, "close"]
            
            # Handle existing position
            if current_position:
                # Check if we should exit based on min holding days
                days_held = (current_date - current_position["entry_date"]).days
                
                if days_held >= self.min_holding_days:
                    # Calculate exit price and P&L
                    exit_price = current_price
                    if current_position["side"] == "LONG":
                        pnl = (exit_price - current_position["entry_price"]) * current_position["size"]
                    else:
                        pnl = (current_position["entry_price"] - exit_price) * current_position["size"]
                    
                    # Apply commission
                    commission = (current_position["entry_price"] + exit_price) * current_position["size"] * self.commission_rate
                    pnl -= commission
                    
                    # Update capital
                    capital += pnl
                    
                    # Record trade
                    trade = {
                        "entry_date": current_position["entry_date"],
                        "exit_date": current_date,
                        "side": current_position["side"],
                        "entry_price": current_position["entry_price"],
                        "exit_price": exit_price,
                        "size": current_position["size"],
                        "pnl": pnl,
                        "commission": commission,
                        "days_held": days_held,
                        "signal_confidence": current_position["signal_confidence"]
                    }
                    trades.append(trade)
                    
                    logger.info(f"Closed {current_position['side']} position: P&L = ${pnl:.2f}")
                    current_position = None
            
            # Handle new position
            if not current_position and signal["decision"] != "FLAT":
                position_size = self.calculate_position_size(signal, current_price, capital)
                
                if position_size > 0:
                    current_position = {
                        "entry_date": current_date,
                        "side": signal["decision"],
                        "entry_price": current_price,
                        "size": position_size,
                        "signal_confidence": signal["confidence"]
                    }
                    
                    logger.info(f"Opened {signal['decision']} position: {position_size:.2f} shares at ${current_price:.2f}")
            
            # Update equity curve
            equity_curve.append(capital)
        
        # Close any remaining position
        if current_position:
            final_date = df.index[-1]
            final_price = df.loc[final_date, "close"]
            days_held = (final_date - current_position["entry_date"]).days
            
            if current_position["side"] == "LONG":
                pnl = (final_price - current_position["entry_price"]) * current_position["size"]
            else:
                pnl = (current_position["entry_price"] - final_price) * current_position["size"]
            
            commission = (current_position["entry_price"] + final_price) * current_position["size"] * self.commission_rate
            pnl -= commission
            capital += pnl
            
            trade = {
                "entry_date": current_position["entry_date"],
                "exit_date": final_date,
                "side": current_position["side"],
                "entry_price": current_position["entry_price"],
                "exit_price": final_price,
                "size": current_position["size"],
                "pnl": pnl,
                "commission": commission,
                "days_held": days_held,
                "signal_confidence": current_position["signal_confidence"]
            }
            trades.append(trade)
        
        # Calculate metrics
        metrics = self.calculate_trade_metrics(trades)
        
        result = {
            "symbol": symbol,
            "start_date": start_date,
            "end_date": end_date,
            "window_size": window_size,
            "step_size": step_size,
            "trades": trades,
            "metrics": metrics,
            "equity_curve": equity_curve
        }
        
        logger.info(f"Completed backtest for {symbol}: {metrics['total_trades']} trades, {metrics['total_return']:.1%} return")
        
        return result
    
    async def run_multi_symbol_backtest(self, symbols: List[str], start_date: str, end_date: str) -> Dict:
        """Run backtests for multiple symbols"""
        logger.info(f"Starting multi-symbol backtest for {len(symbols)} symbols")
        
        results = {}
        leaderboard = []
        
        for symbol in symbols:
            try:
                result = await self.run_walk_forward_backtest(symbol, start_date, end_date)
                if "error" not in result:
                    results[symbol] = result
                    leaderboard.append({
                        "symbol": symbol,
                        "total_return": result["metrics"]["total_return"],
                        "sharpe_ratio": result["metrics"]["sharpe_ratio"],
                        "max_drawdown": result["metrics"]["max_drawdown"],
                        "profit_factor": result["metrics"]["profit_factor"],
                        "total_trades": result["metrics"]["total_trades"],
                        "win_rate": result["metrics"]["win_rate"]
                    })
            except Exception as e:
                logger.error(f"Error backtesting {symbol}: {e}")
        
        # Sort leaderboard by Sharpe ratio
        leaderboard.sort(key=lambda x: x["sharpe_ratio"], reverse=True)
        
        # Save results
        self.save_backtest_results(results, leaderboard)
        
        return {
            "results": results,
            "leaderboard": leaderboard,
            "summary": {
                "total_symbols": len(symbols),
                "successful_backtests": len(results),
                "avg_return": np.mean([r["total_return"] for r in leaderboard]) if leaderboard else 0,
                "avg_sharpe": np.mean([r["sharpe_ratio"] for r in leaderboard]) if leaderboard else 0
            }
        }
    
    def save_backtest_results(self, results: Dict, leaderboard: List[Dict]):
        """Save backtest results to files"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save leaderboard
        leaderboard_df = pd.DataFrame(leaderboard)
        leaderboard_path = self.output_dir / "leaderboard.csv"
        leaderboard_df.to_csv(leaderboard_path, index=False)
        
        # Save detailed results
        walkforward_dir = self.output_dir / "walkforward"
        walkforward_dir.mkdir(exist_ok=True)
        
        for symbol, result in results.items():
            # Save trades
            trades_df = pd.DataFrame(result["trades"])
            trades_path = walkforward_dir / f"{symbol}_trades_{timestamp}.csv"
            trades_df.to_csv(trades_path, index=False)
            
            # Save equity curve
            equity_df = pd.DataFrame({"equity": result["equity_curve"]})
            equity_path = walkforward_dir / f"{symbol}_equity_{timestamp}.csv"
            equity_df.to_csv(equity_path, index=False)
        
        # Save summary
        summary_path = walkforward_dir / f"summary_{timestamp}.json"
        with open(summary_path, 'w') as f:
            json.dump({
                "timestamp": timestamp,
                "leaderboard": leaderboard,
                "symbols_tested": list(results.keys())
            }, f, indent=2, default=str)
        
        logger.info(f"Results saved to {self.output_dir}")

async def main():
    """Main function to run backtests"""
    # Initialize backtest runner
    runner = BacktestRunner()
    
    # Define symbols to test
    symbols = [
        "XAUUSD=X",  # Gold
        "EURUSD=X",  # EUR/USD
        "GBPUSD=X",  # GBP/USD
        "USDJPY=X",  # USD/JPY
        "^GSPC",     # S&P 500
        "BTC-USD"    # Bitcoin
    ]
    
    # Define date range
    start_date = "2020-01-01"
    end_date = "2024-01-01"
    
    logger.info("Starting Trading Suite Backtest Runner")
    logger.info(f"Testing {len(symbols)} symbols from {start_date} to {end_date}")
    
    # Run backtests
    results = await runner.run_multi_symbol_backtest(symbols, start_date, end_date)
    
    # Print summary
    print("\n" + "="*60)
    print("BACKTEST SUMMARY")
    print("="*60)
    print(f"Symbols tested: {results['summary']['total_symbols']}")
    print(f"Successful backtests: {results['summary']['successful_backtests']}")
    print(f"Average return: {results['summary']['avg_return']:.1%}")
    print(f"Average Sharpe ratio: {results['summary']['avg_sharpe']:.3f}")
    
    print("\nLEADERBOARD (Top 5)")
    print("-" * 60)
    for i, entry in enumerate(results['leaderboard'][:5], 1):
        print(f"{i}. {entry['symbol']}: {entry['total_return']:.1%} return, "
              f"{entry['sharpe_ratio']:.3f} Sharpe, {entry['max_drawdown']:.1%} MaxDD")
    
    print(f"\nResults saved to: {runner.output_dir}")

if __name__ == "__main__":
    asyncio.run(main())
