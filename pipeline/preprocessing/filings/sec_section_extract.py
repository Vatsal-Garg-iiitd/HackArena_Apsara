import re
from typing import Dict, Optional

def extract_10k_sections(ticker: str) -> Dict[str, Optional[str]]:
    """
    In a real system, this would use sec-api or edgar package to pull the latest 10-K
    and extract Item 1A (Risk Factors) and Item 7 (MD&A).
    We provide a mock implementation here for the hackathon prototype.
    """
    
    # Mocking SEC EDGAR response
    mock_item_1a = f"Item 1A. Risk Factors for {ticker}.\nOur business is subject to numerous risks. We face intense competition in our core markets. Macroeconomic headwinds such as inflation and rising interest rates may affect consumer demand. Supply chain disruptions could also delay our product shipments."
    
    mock_item_7 = f"Item 7. Management's Discussion and Analysis for {ticker}.\nRevenues increased by 15% due to strong demand in North America. Cost of goods sold improved slightly, leading to margin expansion. We expect this trend to continue, although currency fluctuations remain a headwind."
    
    return {
        "item_1a_risk_factors": mock_item_1a,
        "item_7_mda": mock_item_7
    }
