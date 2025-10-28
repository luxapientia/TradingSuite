import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import httpx
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Page configuration
st.set_page_config(
    page_title="Trading Suite Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

class TradingDashboard:
    """Trading Suite Dashboard using Streamlit"""
    
    def __init__(self):
        self.orchestrator_url = "http://orchestrator:8200"
        self.monolith_url = "http://monolith:8000"
        self.outputs_dir = Path("outputs")
        
    async def get_orchestrator_decision(self, symbol: str, min_conf: float = 0.7) -> dict:
        """Get trading decision from orchestrator"""
        try:
            async with httpx.AsyncClient(timeout=200.0) as client:
                response = await client.post(
                    f"{self.orchestrator_url}/decide",
                    json={"symbol": symbol, "min_conf": min_conf}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get decision for {symbol}: {e}")
            return {"error": str(e)}
    
    async def get_service_status(self) -> dict:
        """Get status of all services"""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(f"{self.orchestrator_url}/services/status")
                response.raise_for_status()
                return response.json()
        except Exception as e:
            logger.error(f"Failed to get service status: {e}")
            return {"error": str(e)}
    
    def load_leaderboard(self) -> pd.DataFrame:
        """Load leaderboard data"""
        leaderboard_path = self.outputs_dir / "leaderboard.csv"
        if leaderboard_path.exists():
            return pd.read_csv(leaderboard_path)
        return pd.DataFrame()
    
    def load_equity_curve(self, symbol: str) -> pd.DataFrame:
        """Load equity curve data for a symbol"""
        walkforward_dir = self.outputs_dir / "walkforward"
        if not walkforward_dir.exists():
            return pd.DataFrame()
        
        # Find the most recent equity curve file for the symbol
        equity_files = list(walkforward_dir.glob(f"{symbol}_equity_*.csv"))
        if not equity_files:
            return pd.DataFrame()
        
        # Get the most recent file
        latest_file = max(equity_files, key=lambda x: x.stat().st_mtime)
        return pd.read_csv(latest_file)
    
    def create_equity_curve_chart(self, df: pd.DataFrame, symbol: str) -> go.Figure:
        """Create equity curve chart"""
        if df.empty:
            fig = go.Figure()
            fig.add_annotation(text="No data available", xref="paper", yref="paper", 
                             x=0.5, y=0.5, showarrow=False)
            return fig
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=list(range(len(df))),
            y=df["equity"],
            mode='lines',
            name=f"{symbol} Equity Curve",
            line=dict(color='blue', width=2)
        ))
        
        fig.update_layout(
            title=f"{symbol} Equity Curve",
            xaxis_title="Time Period",
            yaxis_title="Portfolio Value ($)",
            hovermode='x unified',
            template="plotly_white"
        )
        
        return fig
    
    def create_leaderboard_chart(self, df: pd.DataFrame) -> go.Figure:
        """Create leaderboard bar chart"""
        if df.empty:
            fig = go.Figure()
            fig.add_annotation(text="No data available", xref="paper", yref="paper", 
                             x=0.5, y=0.5, showarrow=False)
            return fig
        
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=df["symbol"],
            y=df["total_return"],
            text=[f"{x:.1%}" for x in df["total_return"]],
            textposition='auto',
            marker_color=['green' if x > 0 else 'red' for x in df["total_return"]]
        ))
        
        fig.update_layout(
            title="Strategy Performance by Symbol",
            xaxis_title="Symbol",
            yaxis_title="Total Return",
            template="plotly_white"
        )
        
        return fig

def main():
    """Main dashboard function"""
    dashboard = TradingDashboard()
    
    # Header
    st.title("📈 Trading Suite Dashboard")
    st.markdown("Real-time trading signal analysis and backtest results")
    
    # Sidebar
    st.sidebar.header("Configuration")
    
    # Symbol selection
    symbols = [
        "XAUUSD=X", "EURUSD=X", "GBPUSD=X", "USDJPY=X",
        "^GSPC", "^DJI", "^IXIC", "BTC-USD", "ETH-USD"
    ]
    selected_symbol = st.sidebar.selectbox("Select Symbol", symbols)
    
    # Confidence threshold
    min_confidence = st.sidebar.slider("Minimum Confidence", 0.0, 1.0, 0.7, 0.05)
    
    # Refresh button
    if st.sidebar.button("🔄 Refresh Data"):
        st.rerun()
    
    # Main content tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Live Signals", "📈 Backtest Results", "🔧 Service Status", "📋 Strategy Details"])
    
    with tab1:
        st.header("Live Trading Signals")
        
        # Get live signal
        with st.spinner("Fetching live signal..."):
            decision = asyncio.run(dashboard.get_orchestrator_decision(selected_symbol, min_confidence))
        
        if "error" in decision:
            st.error(f"Error fetching signal: {decision['error']}")
            st.info("💡 **Troubleshooting Tips:**")
            st.markdown("""
            - Check if all services are running: `docker-compose ps`
            - Verify network connectivity for data fetching
            - Try a different symbol (e.g., AAPL, MSFT, EURUSD=X)
            - Check service logs: `docker-compose logs orchestrator`
            """)
        else:
            # Display decision
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("Decision", decision["decision"])
            
            with col2:
                st.metric("Confidence", f"{decision['confidence']:.3f}")
            
            with col3:
                st.metric("Stop Loss %", f"{decision['sl_pct']:.1%}")
            
            with col4:
                st.metric("Take Profit Multiple", f"{decision['tp_multiple']:.1f}")
            
            # Display components
            st.subheader("Strategy Components")
            components_df = pd.DataFrame(decision["components"])
            st.dataframe(components_df, use_container_width=True)
            
            # Display rationale
            st.subheader("Signal Rationale")
            for component in decision["components"]:
                with st.expander(f"{component['svc'].upper()} - {component['signal']} (Confidence: {component['confidence']:.3f})"):
                    for reason in component["rationale"]:
                        st.write(f"• {reason}")
    
    with tab2:
        st.header("Backtest Results")
        
        # Load leaderboard
        leaderboard_df = dashboard.load_leaderboard()
        
        if not leaderboard_df.empty:
            # Display leaderboard
            st.subheader("Strategy Leaderboard")
            st.dataframe(leaderboard_df, use_container_width=True)
            
            # Create charts
            col1, col2 = st.columns(2)
            
            with col1:
                fig_leaderboard = dashboard.create_leaderboard_chart(leaderboard_df)
                st.plotly_chart(fig_leaderboard, use_container_width=True)
            
            with col2:
                # Equity curve for selected symbol
                equity_df = dashboard.load_equity_curve(selected_symbol)
                if not equity_df.empty:
                    fig_equity = dashboard.create_equity_curve_chart(equity_df, selected_symbol)
                    st.plotly_chart(fig_equity, use_container_width=True)
                else:
                    st.info(f"No equity curve data available for {selected_symbol}")
            
            # Summary statistics
            st.subheader("Summary Statistics")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                avg_return = leaderboard_df["total_return"].mean()
                st.metric("Average Return", f"{avg_return:.1%}")
            
            with col2:
                avg_sharpe = leaderboard_df["sharpe_ratio"].mean()
                st.metric("Average Sharpe", f"{avg_sharpe:.3f}")
            
            with col3:
                avg_drawdown = leaderboard_df["max_drawdown"].mean()
                st.metric("Average Max DD", f"{avg_drawdown:.1%}")
            
            with col4:
                total_trades = leaderboard_df["total_trades"].sum()
                st.metric("Total Trades", f"{total_trades}")
        
        else:
            st.info("No backtest results available. Run the backtest runner to generate results.")
    
    with tab3:
        st.header("Service Status")
        
        # Get service status
        with st.spinner("Checking service status..."):
            status = asyncio.run(dashboard.get_service_status())
        
        if "error" in status:
            st.error(f"Error checking service status: {status['error']}")
        else:
            # Display service status
            for service_name, service_status in status["services"].items():
                with st.expander(f"{service_name.upper()} Service"):
                    if service_status["status"] == "healthy":
                        st.success("✅ Service is healthy")
                        st.json(service_status["response"])
                    else:
                        st.error("❌ Service is unhealthy")
                        st.error(service_status["error"])
    
    with tab4:
        st.header("Strategy Details")
        
        # Strategy information
        strategies = {
            "Supertrend": {
                "description": "ATR-based trend following strategy",
                "parameters": "ATR Period: 10, ATR Multiplier: 3.0",
                "strengths": "Good trend following, low false signals",
                "weaknesses": "Can be slow to react to trend changes"
            },
            "AlphaTrend": {
                "description": "Volatility adaptive trend following with exponential smoothing",
                "parameters": "ATR Period: 14, ATR Multiplier: 2.0, Alpha Period: 21",
                "strengths": "Adaptive to volatility, smoother signals",
                "weaknesses": "May lag in fast-moving markets"
            },
            "Ichimoku": {
                "description": "Cloud-based trend analysis with multiple timeframe confirmation",
                "parameters": "Tenkan: 9, Kijun: 26, Senkou Span B: 52",
                "strengths": "Comprehensive trend analysis, good for longer-term trades",
                "weaknesses": "Complex signals, can be confusing in sideways markets"
            },
            "QQE-SSL-WAE": {
                "description": "Composite strategy requiring 2/3 indicators to agree",
                "parameters": "QQE Period: 14, SSL Period: 10, WAE Period: 20",
                "strengths": "High confidence signals, good filtering",
                "weaknesses": "May miss opportunities due to strict requirements"
            }
        }
        
        for strategy_name, info in strategies.items():
            with st.expander(f"{strategy_name} Strategy"):
                st.write(f"**Description:** {info['description']}")
                st.write(f"**Parameters:** {info['parameters']}")
                st.write(f"**Strengths:** {info['strengths']}")
                st.write(f"**Weaknesses:** {info['weaknesses']}")
        
        # Orchestrator configuration
        st.subheader("Orchestrator Configuration")
        config_info = {
            "Minimum Confidence Threshold": "0.7",
            "Minimum Holding Days": "7",
            "Default Stop Loss %": "2.5%",
            "Default Take Profit Multiple": "1.5x",
            "Signal Aggregation": "Weighted average with confidence gating"
        }
        
        for key, value in config_info.items():
            st.write(f"**{key}:** {value}")

if __name__ == "__main__":
    main()
