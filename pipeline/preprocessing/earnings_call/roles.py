def normalize_role(raw_title: str) -> str:
    """Maps raw earnings call titles to a fixed taxonomy."""
    raw = raw_title.lower()
    if "chief executive" in raw or "ceo" in raw:
        return "CEO"
    if "chief financial" in raw or "cfo" in raw:
        return "CFO"
    if "chief operating" in raw or "coo" in raw:
        return "COO"
    if "investor relations" in raw or "ir" in raw:
        return "IR"
    if "operator" in raw:
        return "Operator"
    if "analyst" in raw or "research" in raw or "capital" in raw:
        return "Analyst"
        
    return "Unknown"
