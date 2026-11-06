"""Money (pure; no pygame). A hero's money is ONE integer in bronze (hero.gold / save "gold");
1 gold = 100 silver = 10000 bronze. These helpers only change how it is shown."""

SILVER = 100          # bronze per silver
GOLD = 100 * SILVER   # bronze per gold


def split(bronze):
    """(gold, silver, bronze) parts of an amount in bronze."""
    bronze = max(0, int(bronze))
    return bronze // GOLD, bronze % GOLD // SILVER, bronze % SILVER


def parts(bronze):
    """The coin parts worth showing, largest first: leading zero coins are dropped, bronze always stays when it is
    the only one. E.g. 12345 -> [(1, "gold"), (23, "silver"), (45, "bronze")], 45 -> [(45, "bronze")]."""
    g, s, b = split(bronze)
    out = [(g, "gold"), (s, "silver"), (b, "bronze")]
    while len(out) > 1 and out[0][0] == 0:
        out.pop(0)
    return out


def format_short(bronze):
    """'1g 23s 45b' (floating text, compact HUD)."""
    return " ".join(f"{n}{coin[0]}" for n, coin in parts(bronze))


def format_long(bronze):
    """'1 gold 23 silver 45 bronze' (speech, panels)."""
    return " ".join(f"{n} {coin}" for n, coin in parts(bronze))
