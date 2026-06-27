from typing import Optional
from abc import ABC, abstractmethod
import os
import requests

class TranscriptSource(ABC):
    @abstractmethod
    def fetch_latest_transcript(self, ticker: str) -> Optional[str]:
        pass

class MockTranscriptSource(TranscriptSource):
    """A mock source for testing preprocessing without burning API keys."""
    def fetch_latest_transcript(self, ticker: str) -> Optional[str]:
        return """
Operator: Good afternoon, and welcome to the Q1 2026 Earnings Conference Call. I will now turn the call over to Investor Relations.

Jane Doe - Investor Relations:
Thank you, operator. Welcome everyone. Before we begin, please note that this call contains forward-looking statements that are subject to risks and uncertainties. Actual results may differ materially. Now, I'll turn it over to our CEO, John Smith.

John Smith - Chief Executive Officer:
Thank you, Jane. We had a strong quarter with record margins. Our outlook remains positive despite macro headwinds. I'll hand it to our CFO.

Alice Johnson - Chief Financial Officer:
Thanks, John. Revenue grew 15% year over year. We are raising our full-year guidance based on strong demand.

Operator: We will now begin the question-and-answer session. First question comes from Bob at Analyst Firm.

Bob - Analyst:
Can you talk more about the margin expansion?

Alice Johnson (CFO):
Yes, our margin expansion was primarily driven by lower opex and pricing discipline.
"""

class FinnhubTranscriptSource(TranscriptSource):
    def __init__(self):
        self.api_key = os.getenv("FINNHUB_API_KEY")
        
    def fetch_latest_transcript(self, ticker: str) -> Optional[str]:
        if not self.api_key:
            print("No Finnhub API key found.")
            return None
        # Example API call to Finnhub for transcripts (pseudo-endpoint as it might vary or require premium)
        url = f"https://finnhub.io/api/v1/stock/transcripts?symbol={ticker}&token={self.api_key}"
        try:
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                if data and isinstance(data, list) and len(data) > 0:
                    # Need to reconstruct raw transcript from their format
                    raw_text = ""
                    for item in data[0].get('transcript', []):
                        raw_text += f"{item.get('name', 'Unknown')}: {item.get('speech', '')}\n\n"
                    return raw_text
        except Exception as e:
            print(f"Error fetching from Finnhub: {e}")
        return None

# Factory or default selection
def get_transcript_source() -> TranscriptSource:
    return MockTranscriptSource()
