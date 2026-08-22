"""Deterministic, project-stable printable symbols for used DMC colors."""
from itertools import product

SAFE_DIGITS="234679"
SAFE_UPPER="ACDEFGHJKLMNPQRTUVWXYZ"
SAFE_LOWER="abcdefghijkmnpqrtuvwxyz"
SAFE_PUNCT="@#$%&*+=?<>"
SINGLE_SYMBOLS=tuple(SAFE_DIGITS+SAFE_UPPER+SAFE_LOWER+SAFE_PUNCT)
MULTI_SYMBOLS=tuple(a+b for a,b in product(SAFE_UPPER,SAFE_DIGITS+SAFE_UPPER))
SYMBOL_POOL=SINGLE_SYMBOLS+MULTI_SYMBOLS


def _code_key(code):
    return (0,int(code)) if str(code).isdigit() else (1,str(code))


def assign_symbols(used_codes,existing=None):
    """Return unique symbols for used codes, preserving valid existing assignments."""
    codes=sorted({code for code in used_codes if code is not None},key=_code_key)
    if len(codes)>len(SYMBOL_POOL):raise ValueError(f"Pattern uses {len(codes)} colors but only {len(SYMBOL_POOL)} printable symbols are available.")
    existing=existing or {};mapping={};taken=set()
    for code in codes:
        symbol=existing.get(code)
        if symbol in SYMBOL_POOL and symbol not in taken:mapping[code]=symbol;taken.add(symbol)
    available=(symbol for symbol in SYMBOL_POOL if symbol not in taken)
    for code in codes:
        if code not in mapping:mapping[code]=next(available)
    return mapping


def ensure_pattern_symbols(pattern):
    mapping=assign_symbols(pattern.usage,pattern.metadata.get("symbol_mapping"))
    pattern.metadata["symbol_mapping"]=mapping
    return mapping


def symbol_text_rgb(rgb):
    """Choose black or white using WCAG relative-luminance contrast."""
    channels=[]
    for value in rgb:
        channel=value/255.0;channels.append(channel/12.92 if channel<=0.04045 else ((channel+.055)/1.055)**2.4)
    luminance=.2126*channels[0]+.7152*channels[1]+.0722*channels[2]
    black_contrast=(luminance+.05)/.05;white_contrast=1.05/(luminance+.05)
    return (0,0,0) if black_contrast>=white_contrast else (255,255,255)
