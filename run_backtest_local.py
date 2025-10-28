#!/usr/bin/env python3
"""
Standalone backtest runner that can work without Docker services
This creates sample data to demonstrate the dashboard functionality
"""

import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_sample_backtest_data():
    """Create sample backtest data for demonstration"""
    
    # Create outputs directory
    output_dir = Path("outputs")
    output_dir.mkdir(exist_ok=True)
    
    # Create walkforward subdirectory
    walkforward_dir = output_dir / "walkforward"
    walkforward_dir.mkdir(exist_ok=True)
    
    # Sample symbols and their performance
    symbols_data = [
        {"symbol": "XAUUSD=X", "return": 0.156, "sharpe": 1.234, "drawdown": -0.089, "trades": 45, "win_rate": 0.622},
        {"symbol": "EURUSD=X", "return": 0.089, "sharpe": 0.987, "drawdown": -0.067, "trades": 38, "win_rate": 0.579},
        {"symbol": "GBPUSD=X", "return": 0.123, "sharpe": 1.123, "drawdown": -0.078, "trades": 42, "win_rate": 0.595},
        {"symbol": "USDJPY=X", "return": 0.067, "sharpe": 0.876, "drawdown": -0.092, "trades": 35, "win_rate": 0.543},
        {"symbol": "^GSPC", "return": 0.234, "sharpe": 1.456, "drawdown": -0.123, "trades": 52, "win_rate": 0.654},
        {"symbol": "BTC-USD", "return": 0.345, "sharpe": 1.789, "drawdown": -0.156, "trades": 48, "win_rate": 0.688},
    ]
    
    # Create leaderboard data
    leaderboard_data = []
    for data in symbols_data:
        leaderboard_data.append({
            "symbol": data["symbol"],
            "total_return": data["return"],
            "sharpe_ratio": data["sharpe"],
            "max_drawdown": data["drawdown"],
            "profit_factor": round(1.0 + data["return"] * 0.5, 3),  # Simulate profit factor
            "total_trades": data["trades"],
            "win_rate": data["win_rate"]
        })
    
    # Save leaderboard
    leaderboard_df = pd.DataFrame(leaderboard_data)
    leaderboard_path = output_dir / "leaderboard.csv"
    leaderboard_df.to_csv(leaderboard_path, index=False)
    logger.info(f"Created leaderboard: {leaderboard_path}")
    
    # Create equity curves for each symbol
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for data in symbols_data:
        symbol = data["symbol"]
        
        # Generate realistic equity curve
        initial_capital = 100000
        final_capital = initial_capital * (1 + data["return"])
        
        # Create equity curve with some volatility
        periods = 252  # Trading days
        returns = np.random.normal(data["return"] / periods, 0.02, periods)
        equity_curve = [initial_capital]
        
        for ret in returns:
            equity_curve.append(equity_curve[-1] * (1 + ret))
        
        # Ensure final value matches target
        equity_curve[-1] = final_capital
        
        # Save equity curve
        equity_df = pd.DataFrame({"equity": equity_curve})
        equity_path = walkforward_dir / f"{symbol}_equity_{timestamp}.csv"
        equity_df.to_csv(equity_path, index=False)
        logger.info(f"Created equity curve for {symbol}: {equity_path}")
        
        # Create sample trades data
        trades_data = []
        num_trades = data["trades"]
        
        for i in range(num_trades):
            # Generate random trade data
            entry_price = 100 + np.random.normal(0, 20)
            exit_price = entry_price * (1 + np.random.normal(0, 0.05))
            side = np.random.choice(["LONG", "SHORT"])
            
            if side == "LONG":
                pnl = (exit_price - entry_price) * 100
            else:
                pnl = (entry_price - exit_price) * 100
            
            trades_data.append({
                "entry_date": (datetime.now() - timedelta(days=np.random.randint(1, 365))).strftime("%Y-%m-%d"),
                "exit_date": (datetime.now() - timedelta(days=np.random.randint(1, 30))).strftime("%Y-%m-%d"),
                "side": side,
                "entry_price": round(entry_price, 2),
                "exit_price": round(exit_price, 2),
                "size": 100,
                "pnl": round(pnl, 2),
                "commission": round((entry_price + exit_price) * 100 * 0.001, 2),
                "days_held": np.random.randint(1, 30),
                "signal_confidence": round(np.random.uniform(0.6, 0.95), 3)
            })
        
        # Save trades
        trades_df = pd.DataFrame(trades_data)
        trades_path = walkforward_dir / f"{symbol}_trades_{timestamp}.csv"
        trades_df.to_csv(trades_path, index=False)
        logger.info(f"Created trades for {symbol}: {trades_path}")
    
    # Create summary file
    summary_data = {
        "timestamp": timestamp,
        "symbols_tested": [data["symbol"] for data in symbols_data],
        "total_symbols": len(symbols_data),
        "avg_return": np.mean([data["return"] for data in symbols_data]),
        "avg_sharpe": np.mean([data["sharpe"] for data in symbols_data]),
        "best_performer": max(symbols_data, key=lambda x: x["return"])["symbol"],
        "worst_performer": min(symbols_data, key=lambda x: x["return"])["symbol"]
    }
    
    summary_path = walkforward_dir / f"summary_{timestamp}.json"
    with open(summary_path, 'w') as f:
        json.dump(summary_data, f, indent=2)
    
    logger.info(f"Created summary: {summary_path}")
    
    print("\n" + "="*60)
    print("SAMPLE BACKTEST DATA CREATED")
    print("="*60)
    print(f"Symbols tested: {len(symbols_data)}")
    print(f"Average return: {summary_data['avg_return']:.1%}")
    print(f"Average Sharpe ratio: {summary_data['avg_sharpe']:.3f}")
    print(f"Best performer: {summary_data['best_performer']}")
    print(f"Worst performer: {summary_data['worst_performer']}")
    print(f"\nResults saved to: {output_dir}")
    print("\nYou can now refresh your dashboard to see the backtest results!")

if __name__ == "__main__":
    create_sample_backtest_data()
