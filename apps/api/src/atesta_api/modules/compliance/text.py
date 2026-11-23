"""Text input shared by the recorded routines: whitespace collapsed, required fields non-empty."""


def collapse(value: str) -> str:
    return " ".join(value.split())


def filled(value: str) -> str:
    """Collapse whitespace and refuse what is left empty (422, never a database check error)."""
    cleaned = collapse(value)
    if not cleaned:
        raise ValueError("the text is empty")
    return cleaned
