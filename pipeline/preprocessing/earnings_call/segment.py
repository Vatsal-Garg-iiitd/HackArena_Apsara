import re
from typing import List, Dict, Any
from .roles import normalize_role

# Broaden speaker pattern to just grab everything up to the first colon.
SPEAKER_PATTERN = re.compile(r'^([^:\n]{2,60}):\s*(.*)', re.MULTILINE)

QA_BOUNDARY_PATTERNS = [
    re.compile(r"question.and.answer session", re.IGNORECASE),
    re.compile(r"first question (comes|will come) from", re.IGNORECASE),
    re.compile(r"we('ll| will) now (begin|open) the (question|q&a)", re.IGNORECASE),
]

def parse_speaker_info(raw_speaker: str) -> tuple[str, str]:
    """Extracts name and role from raw speaker string (e.g. 'John Doe - CEO' or 'Jane (CFO)')"""
    raw_speaker = raw_speaker.strip()
    
    # Try dash format: Name - Role or Role - Name
    if " - " in raw_speaker:
        parts = raw_speaker.split(" - ", 1)
        name, role = parts[0].strip(), parts[1].strip()
        # If it says Operator - [Name], flip it or handle it
        if "Operator" in name or "Operator" in role:
            return name if "Operator" not in name else role, "Operator"
        return name, role
        
    # Try parens format: Name (Role)
    paren_match = re.search(r'^(.*?)\s*\((.*?)\)$', raw_speaker)
    if paren_match:
        return paren_match.group(1).strip(), paren_match.group(2).strip()
        
    # Default
    if "Operator" in raw_speaker:
        return raw_speaker, "Operator"
        
    return raw_speaker, "Unknown"


def segment_transcript(raw_text: str) -> List[Dict[str, Any]]:
    lines = raw_text.split('\n')
    
    segments = []
    current_speaker = "Unknown"
    current_role = "Unknown"
    current_section = "prepared"
    current_text = []
    
    def flush_segment():
        if current_text:
            text = " ".join(current_text).strip()
            if text:
                segments.append({
                    "speaker": current_speaker,
                    "role": normalize_role(current_role),
                    "section": current_section,
                    "text": text
                })
            current_text.clear()

    for line in lines:
        line_clean = line.strip()
        if not line_clean:
            continue
            
        # Check Q&A boundary
        if current_section == "prepared":
            for pat in QA_BOUNDARY_PATTERNS:
                if pat.search(line_clean):
                    current_section = "qa"
                    break
                    
        # Check if line is a new speaker
        match = SPEAKER_PATTERN.match(line_clean)
        if match:
            flush_segment()
            
            raw_speaker = match.group(1)
            name, role = parse_speaker_info(raw_speaker)
            
            current_speaker = name
            current_role = role
                
            remainder = match.group(2).strip()
            if remainder:
                current_text.append(remainder)
        else:
            current_text.append(line_clean)
            
    flush_segment()
    return segments

def filter_qa_relevance(segments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filters Q&A segments based on finance-salient keywords."""
    keywords = {
        "guidance", "margin", "headwind", "tailwind", "capex", "opex", 
        "growth", "churn", "backlog", "buyback", "dividend", "pricing", 
        "demand", "supply", "inventory", "outlook", "forecast"
    }
    
    filtered = []
    for seg in segments:
        if seg["section"] == "qa" and seg["role"] != "Operator":
            words = set(re.findall(r'\b\w+\b', seg["text"].lower()))
            if not keywords.intersection(words):
                continue
        filtered.append(seg)
    return filtered
