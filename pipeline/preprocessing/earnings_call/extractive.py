import re
from typing import Dict, List

def split_into_sentences(text: str) -> List[str]:
    """Simple regex based sentence splitter for prototype."""
    # Split on period, exclamation, or question mark followed by a space and capital letter
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [s.strip() for s in sentences if s.strip()]

def extract_contextual_sentences(sentences: List[str], keywords: List[str]) -> List[str]:
    """
    Extracts sentences containing any of the keywords, plus the sentence 
    immediately before and after for context.
    """
    extracted_indices = set()
    keyword_pattern = re.compile(r'\b(?:' + '|'.join(keywords) + r')\b', re.IGNORECASE)
    
    for i, sent in enumerate(sentences):
        if keyword_pattern.search(sent):
            # Add previous, current, next
            if i > 0:
                extracted_indices.add(i - 1)
            extracted_indices.add(i)
            if i < len(sentences) - 1:
                extracted_indices.add(i + 1)
                
    # Reconstruct in order
    sorted_indices = sorted(list(extracted_indices))
    return [sentences[i] for i in sorted_indices]

def summarize_prepared_remarks(prepared_text: str) -> Dict[str, List[str]]:
    sentences = split_into_sentences(prepared_text)
    
    topic_keywords = {
        "guidance": ["guidance", "forecast", "expect", "project", "outlook"],
        "margin": ["margin", "compression", "expansion", "basis points", "bps"],
        "competition": ["competitor", "competition", "market share", "rival"],
        "macro": ["headwind", "tailwind", "inflation", "supply chain", "interest rate"]
    }
    
    categorized = {}
    
    for topic, keywords in topic_keywords.items():
        extracted = extract_contextual_sentences(sentences, keywords)
        categorized[topic] = extracted
        
    return categorized
