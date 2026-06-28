from datetime import date
from typing import Dict, Any
from .source import get_transcript_source
from .segment import segment_transcript, filter_qa_relevance
from .sentiment_lexicon import analyze_sentiment
from .extractive import summarize_prepared_remarks

def process_latest_earnings_call(ticker: str, source: str = "auto") -> Dict[str, Any]:
    transcript_source = get_transcript_source(source)
    raw_transcript = transcript_source.fetch_latest_transcript(ticker)
    
    if not raw_transcript:
        return {}
        
    segments = segment_transcript(raw_transcript)
    
    prepared = [s for s in segments if s["section"] == "prepared"]
    qa = [s for s in segments if s["section"] == "qa"]
    
    # Filter Q&A
    filtered_qa = filter_qa_relevance(qa)
    
    # Analyze Sentiment
    full_text = " ".join([s["text"] for s in segments])
    sentiment = analyze_sentiment(full_text)
    
    # Condense Prepared Remarks
    prepared_text = " ".join([s["text"] for s in prepared])
    prepared_condensed = summarize_prepared_remarks(prepared_text)
    
    # Format QA for output
    qa_excerpts = []
    for s in filtered_qa:
        qa_excerpts.append({
            "speaker_role": s["role"],
            "speaker_name": s["speaker"],
            "text": s["text"]
        })
        
    # Construct final schema
    result = {
        "ticker": ticker,
        "quarter": "Recent", # Hardcoded for prototype
        "call_date": str(date.today()), # Hardcoded for prototype
        "prepared_remarks_excerpts": prepared_condensed,
        "qa_excerpts": qa_excerpts,
        "sentiment": sentiment,
        "token_estimate": len(full_text.split()) # rough estimate
    }
    return result
