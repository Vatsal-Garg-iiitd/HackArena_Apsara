import re
from typing import Dict, Any

# Mock version of Loughran-McDonald Dictionary for prototype purposes
# In production, load from the full LM CSV file.
LM_DICT = {
    "positive": {"achieve", "advantage", "better", "creative", "efficiency", "empower", "excellent", "favorable", "growth", "improvement", "innovation", "opportunities", "profitability", "progress", "record", "strong", "success", "valuable"},
    "negative": {"adverse", "against", "bad", "challenge", "decline", "default", "deficit", "deplete", "deteriorate", "difficult", "disappoint", "down", "fail", "headwind", "loss", "negative", "poor", "risk", "shortfall", "weak"},
    "uncertainty": {"ambiguity", "anomaly", "approximate", "assume", "believe", "contingent", "could", "depend", "doubt", "estimate", "expect", "fluctuate", "guess", "may", "might", "pending", "possible", "predict", "probably", "risk", "uncertain", "volatile"},
    "litigious": {"acquaint", "affidavit", "allegation", "appeal", "arbitration", "breach", "claim", "complaint", "condemn", "convict", "court", "crime", "damage", "defend", "defendant", "deposition", "dispute", "evidence", "felony", "fraud", "guilty", "hearing", "illegal", "injunction", "investigate", "judge", "jurisdiction", "lawsuit", "legal", "liability", "litigate", "petition", "plaintiff", "plea", "prosecute", "punish", "settlement", "subpoena", "sue", "testify", "trial", "violation"}
}

def analyze_sentiment(text: str) -> Dict[str, Any]:
    words = re.findall(r'\b\w+\b', text.lower())
    
    pos_count = 0
    neg_count = 0
    unc_count = 0
    lit_count = 0
    
    for word in words:
        if word in LM_DICT["positive"]: pos_count += 1
        if word in LM_DICT["negative"]: neg_count += 1
        if word in LM_DICT["uncertainty"]: unc_count += 1
        if word in LM_DICT["litigious"]: lit_count += 1
        
    total_scored = pos_count + neg_count
    net_sentiment = (pos_count - neg_count) / total_scored if total_scored > 0 else 0.0
    
    return {
        "positive": pos_count,
        "negative": neg_count,
        "uncertainty": unc_count,
        "litigious": lit_count,
        "net_sentiment": net_sentiment
    }
