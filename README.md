# Trading Suite

A complete **multi-service trading research and signal orchestration system** built with FastAPI microservices, Docker orchestration, and comprehensive backtesting capabilities.

## 🏗️ Architecture Overview

The Trading Suite consists of:

- **Monolith Service**: Price data retrieval and caching
- **Strategy Microservices**: Four independent trading strategies
- **Orchestrator**: Signal aggregation and decision making
- **Dashboard**: Real-time visualization and monitoring
- **Backtest Runner**: Walk-forward testing and performance analysis

## 🚀 Quick Start

### Prerequisites

- Docker and Docker Compose
- Git

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd trading-suite
   ```

2. **Start all services**
   ```bash
   docker-compose up --build
   ```

3. **Run smoke tests**
   ```bash
   chmod +x scripts/smoke.sh
   ./scripts/smoke.sh
   ```

4. **Access the dashboard**
   Open http://localhost:8300 in your browser

## 📊 Services Overview

### Monolith Service (Port 8000)
- **Purpose**: Centralized price data retrieval and caching
- **Endpoints**:
  - `GET /health` - Health check
  - `GET /prices?symbol=XAUUSD=X&start=2024-01-01` - OHLC data
  - `GET /symbols` - Available trading symbols
- **Features**: 1-hour caching, yfinance integration, error handling

### Strategy Microservices

#### Supertrend Service (Port 8101)
- **Strategy**: ATR-based trend following
- **Parameters**: ATR Period: 10, ATR Multiplier: 3.0
- **Endpoint**: `POST /signal` - Generate trading signal

#### AlphaTrend Service (Port 8102)
- **Strategy**: Volatility adaptive trend following with exponential smoothing
- **Parameters**: ATR Period: 14, ATR Multiplier: 2.0, Alpha Period: 21
- **Endpoint**: `POST /signal` - Generate trading signal

#### Ichimoku Service (Port 8103)
- **Strategy**: Cloud-based trend analysis with multiple timeframe confirmation
- **Parameters**: Tenkan: 9, Kijun: 26, Senkou Span B: 52
- **Endpoint**: `POST /signal` - Generate trading signal

#### QQE-SSL-WAE Service (Port 8104)
- **Strategy**: Composite strategy requiring 2/3 indicators to agree
- **Parameters**: QQE Period: 14, SSL Period: 10, WAE Period: 20
- **Endpoint**: `POST /signal` - Generate trading signal

### Orchestrator Service (Port 8200)
- **Purpose**: Signal aggregation and decision making
- **Endpoints**:
  - `GET /health` - Health check
  - `POST /decide` - Make trading decision
  - `GET /services/status` - Check all service status
- **Features**: Confidence gating (≥0.70), min holding days (≥7), weighted aggregation

### Dashboard Service (Port 8300)
- **Purpose**: Real-time visualization and monitoring
- **Features**: Live signals, backtest results, service status, strategy details
- **Technology**: Streamlit with Plotly charts

## 🔧 Configuration

### Environment Variables

Copy `env.example` to `.env` and customize:

```bash
cp env.example .env
```

Key configurations:
- `DEFAULT_MIN_CONFIDENCE=0.7` - Minimum confidence threshold
- `DEFAULT_MIN_HOLDING_DAYS=7` - Minimum holding period
- `DEFAULT_SL_PCT=0.025` - Default stop loss percentage
- `DEFAULT_TP_MULTIPLE=1.5` - Default take profit multiple

### Service URLs

All services communicate via Docker network:
- Monolith: `http://monolith:8000`
- Orchestrator: `http://orchestrator:8200`
- Strategies: `http://{service_name}:8000` (internal ports)

## 📈 Usage Examples

### Get Trading Signal

```bash
curl -X POST "http://localhost:8200/decide" \
  -H "Content-Type: application/json" \
  -d '{"symbol": "XAUUSD=X", "min_conf": 0.7}'
```

Response:
```json
{
  "decision": "LONG",
  "confidence": 0.82,
  "components": [
    {"svc": "supertrend", "signal": "LONG", "confidence": 0.8},
    {"svc": "alphatrend", "signal": "LONG", "confidence": 0.85},
    {"svc": "ichimoku", "signal": "FLAT", "confidence": 0.6},
    {"svc": "qqe_ssl_wae", "signal": "LONG", "confidence": 0.8}
  ],
  "sl_pct": 0.025,
  "tp_multiple": 1.5
}
```

### Get Price Data

```bash
curl "http://localhost:8000/prices?symbol=XAUUSD=X&start=2024-01-01"
```

### Check Service Status

```bash
curl "http://localhost:8200/services/status"
```

## 🧪 Backtesting

### Run Backtests

```bash
# Start services first
docker-compose up -d

# Run backtest runner
python backtests/run_backtests.py
```

### Backtest Configuration

The backtest runner tests multiple symbols with walk-forward analysis:
- **Window Size**: 252 days (1 year)
- **Step Size**: 21 days (1 month)
- **Initial Capital**: $100,000
- **Commission**: 0.1%
- **Risk per Trade**: 2%

### Output Files

Results are saved in `outputs/`:
- `leaderboard.csv` - Performance summary
- `walkforward/{symbol}_trades_{timestamp}.csv` - Individual trades
- `walkforward/{symbol}_equity_{timestamp}.csv` - Equity curves
- `walkforward/summary_{timestamp}.json` - Test summary

## 📊 Dashboard Features

### Live Signals Tab
- Real-time trading signals
- Strategy component analysis
- Signal rationale and confidence

### Backtest Results Tab
- Strategy leaderboard
- Performance charts
- Equity curve visualization
- Summary statistics

### Service Status Tab
- Health monitoring
- Service availability
- Error reporting

### Strategy Details Tab
- Strategy descriptions
- Parameter explanations
- Strengths and weaknesses

## 🔍 Monitoring and Debugging

### Logs

View service logs:
```bash
docker-compose logs -f [service_name]
```

### Health Checks

All services expose health endpoints:
- Monolith: `http://localhost:8000/health`
- Orchestrator: `http://localhost:8200/health`
- Strategies: `http://localhost:8001-8004/health`

### Smoke Tests

Run comprehensive tests:
```bash
./scripts/smoke.sh
```

## 🛠️ Development

### Adding New Strategies

1. Create new service directory in `services/`
2. Implement strategy logic in `service.py`
3. Add Dockerfile and requirements.txt
4. Update docker-compose.yml
5. Add service URL to orchestrator

### Customizing Parameters

Each strategy exposes a `/parameters` endpoint for configuration:
```bash
curl "http://localhost:8001/parameters"
```

### Extending the Dashboard

The dashboard is built with Streamlit and can be extended by modifying `dashboard/app.py`.

## 📚 API Documentation

### FastAPI Auto-Docs

Each service provides interactive API documentation:
- Monolith: http://localhost:8000/docs
- Orchestrator: http://localhost:8200/docs
- Strategies: http://localhost:8101-8104/docs

## 🚨 Troubleshooting

### Common Issues

1. **Services not starting**: Check Docker logs and ensure all dependencies are installed
2. **No price data**: Verify internet connection and symbol format
3. **Low confidence signals**: Adjust `min_conf` parameter or check market conditions
4. **Dashboard not loading**: Ensure Streamlit is properly installed and port 8300 is available

### Performance Optimization

- Adjust caching duration in monolith service
- Optimize strategy parameters for your use case
- Use appropriate timeframes for your trading style
- Monitor memory usage with `docker stats`

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📞 Support

For issues and questions:
- Create an issue in the repository
- Check the troubleshooting section
- Review the API documentation

---

**Happy Trading! 📈**
