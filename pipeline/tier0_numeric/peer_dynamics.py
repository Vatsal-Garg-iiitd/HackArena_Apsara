import yfinance as yf
from pipeline.schemas.tier0 import PeerDynamics
from pipeline.tier0_numeric.technicals import get_technicals

# Simple mock mapping for common tickers to avoid needing a complex API call for peers in this prototype
MOCK_PEERS = {
    "AAPL": ["MSFT", "GOOGL", "META"],
    "MSFT": ["AAPL", "GOOGL", "AMZN"],
    "GOOGL": ["META", "MSFT", "AMZN"],
    "TSLA": ["F", "GM", "RIVN"]
}

def get_peer_dynamics(ticker_symbol: str) -> PeerDynamics:
    peers = MOCK_PEERS.get(ticker_symbol, [])
    
    if not peers:
        # If no peers, return defaults
        return PeerDynamics(
            peer_tickers=[],
            relative_sharpe=0.0,
            relative_volatility=0.0,
            relative_drawdown=0.0
        )
        
    try:
        base_tech = get_technicals(ticker_symbol)
        
        peer_sharpes = []
        peer_vols = []
        peer_dds = []
        
        for peer in peers:
            peer_tech = get_technicals(peer)
            peer_sharpes.append(peer_tech.sharpe_60d)
            peer_vols.append(peer_tech.volatility_60d)
            peer_dds.append(peer_tech.max_drawdown_60d)
            
        avg_peer_sharpe = sum(peer_sharpes) / len(peer_sharpes) if peer_sharpes else 0
        avg_peer_vol = sum(peer_vols) / len(peer_vols) if peer_vols else 0
        avg_peer_dd = sum(peer_dds) / len(peer_dds) if peer_dds else 0
        
        return PeerDynamics(
            peer_tickers=peers,
            relative_sharpe=base_tech.sharpe_60d - avg_peer_sharpe,
            relative_volatility=base_tech.volatility_60d - avg_peer_vol,
            relative_drawdown=base_tech.max_drawdown_60d - avg_peer_dd
        )
    except Exception as e:
        print(f"Error computing peer dynamics for {ticker_symbol}: {e}")
        return PeerDynamics(
            peer_tickers=peers,
            relative_sharpe=0.0,
            relative_volatility=0.0,
            relative_drawdown=0.0
        )
