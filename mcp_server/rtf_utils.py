from striprtf.striprtf import rtf_to_text


def rtf_to_markdown(rtf_content: str) -> str:
    """Converts Scrivener RTF content to clean plain text/markdown."""
    if not rtf_content:
        return ""
    try:
        # Convert RTF to plain text using striprtf
        text = rtf_to_text(rtf_content)
        return text.strip()
    except Exception as e:
        return f"[Error parsing RTF: {e}]\n\n{rtf_content}"

def text_to_rtf(text: str) -> str:
    """Converts plain text/markdown to Scrivener-compatible RTF."""
    if not text:
        text = ""
    
    # Normalize carriage returns and line endings to prevent swallowed formatting inside Scrivener
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    
    escaped = []
    for char in text:
        if char == '\\':
            escaped.append('\\\\')
        elif char == '{':
            escaped.append('\\{')
        elif char == '}':
            escaped.append('\\}')
        elif char == '\n':
            escaped.append('\\par\n')
        elif ord(char) > 65535:
            # Character is outside the BMP, encode as UTF-16 surrogate pair
            code = ord(char)
            high = (code - 0x10000) // 0x400 + 0xD800
            low = (code - 0x10000) % 0x400 + 0xDC00
            high_signed = high - 65536 if high > 32767 else high
            low_signed = low - 65536 if low > 32767 else low
            escaped.append(f'\\u{high_signed}?\\u{low_signed}?')
        elif ord(char) > 127:
            # Convert to signed 16-bit unicode value for RTF
            code = ord(char)
            if code > 32767:
                code -= 65536
            escaped.append(f'\\u{code}?')
        else:
            escaped.append(char)
            
    escaped_str = "".join(escaped)
    
    # Return a clean Scrivener-friendly RTF template
    return (
        r"{\rtf1\ansi\deff0{\fonttbl{\f0\fnil\fcharset0 Arial;}}"
        r"\viewkind4\uc1\pard\lang1033\f0\fs24 "
        f"{escaped_str}"
        r"}"
    )
