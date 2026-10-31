"""Finding co-op games on the home network (no pygame).

There is no broadcasting and nothing listens on joiners' machines. The joiner's game scans its own /24
block (e.g. 192.168.1.1-254), knocks on the game port of each address with a short timeout, and asks
anything that answers "what game is this?" ({"t": "info"}). Hosts reply with a one-line description and
close the connection; nothing joins until the player picks a game.
"""
import ipaddress
import json
import socket
from concurrent.futures import ThreadPoolExecutor

from game.net.protocol import PROTOCOL_VERSION, LineBuffer, encode

LOOPBACK = "127.0.0.1"


def lan_address():
    """This machine's home-network IPv4 address (e.g. '192.168.1.23'), or None if it has none.

    Uses the routing table only: connect() on a UDP socket picks the outgoing interface without sending
    anything. Only private addresses count (we never host on a public address)."""
    for probe in ("192.168.0.1", "10.0.0.1", "172.16.0.1"):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((probe, 9))
                ip = s.getsockname()[0]
        except OSError:
            continue
        try:
            addr = ipaddress.IPv4Address(ip)
        except ValueError:
            continue
        if addr.is_private and not addr.is_loopback and not addr.is_link_local:
            return ip
    return None


def describe(info):
    """'Quinn (Lv 7) - Northshire (8pp) (LAN 192.168.1.23) · 2/4 players'"""
    where = "this computer" if info["address"].startswith("127.") else f"LAN {info['address']}"
    return (f"{info['host_name']} (Lv {info['host_level']}) - {info['map_name']} ({info['pp']}pp) ({where})"
            f" · {info['players']}/{info['max_players']} players")


def probe(address, port, timeout=0.4):
    """Ask one address whether it hosts a game. Returns the info dict (plus "address"), or None."""
    try:
        with socket.create_connection((address, port), timeout=timeout) as s:
            s.settimeout(timeout * 2)
            s.sendall(encode({"t": "info", "v": PROTOCOL_VERSION}))
            buf = LineBuffer()
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    return None
                msgs = buf.feed(chunk)
                if msgs:
                    msg = msgs[0]
                    break
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if msg.get("t") != "info" or not isinstance(msg.get("map_name"), str):
        return None
    keep = ("host_name", "host_level", "map_name", "pp", "players", "max_players", "v")
    info = {k: msg.get(k) for k in keep}
    if not all(isinstance(info[k], int) for k in ("host_level", "pp", "players", "max_players")):
        return None
    info["host_name"] = str(info["host_name"])[:20]
    info["map_name"] = info["map_name"][:40]
    info["address"] = address
    info["compatible"] = info["v"] == PROTOCOL_VERSION
    return info


def scan(port, prefix=None, include_local=True, timeout=1.0, passes=2):
    """Find games: this computer first, then every address in this machine's /24 home-network block.
    `prefix` ("192.168.1") overrides the block (tests use "127.0.0"). Returns a list of info dicts.

    Knocking on 254 addresses at once makes the OS look all of them up on the network at the same moment,
    which can delay even real hosts — so the timeout is generous and, if nothing answered, a second pass
    retries (the addresses that exist answer fast the second time)."""
    addresses = []
    if include_local:
        addresses.append(LOOPBACK)
    if prefix is None:
        mine = lan_address()
        if mine:
            prefix = mine.rsplit(".", 1)[0]
    if prefix:
        addresses += [f"{prefix}.{i}" for i in range(1, 255) if f"{prefix}.{i}" != LOOPBACK]
    found = []
    with ThreadPoolExecutor(max_workers=128) as pool:
        for _ in range(passes):
            results = list(pool.map(lambda a: probe(a, port, timeout), addresses))
            # A this-computer host listens on 127.0.0.1 only and a home-network host on its LAN address
            # only, so the same game never answers twice.
            found = [info for info in results if info]
            if found:
                break
    return found
