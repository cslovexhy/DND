# Playing together on the home network

## One-time setup on each computer (Mac or Windows)

1. Download (or `git clone`) this repository. Every computer needs the **same version** of the game —
   update everyone together. Games from a different version show up in red on the Join screen.
2. Install Python 3 if the computer doesn't have it (https://www.python.org/downloads/; on Windows tick
   "Add Python to PATH").
3. Start the game: **Mac** `./run.sh` · **Windows** double-click `run.bat`.
   The first start sets everything up (creates `.venv`, installs pygame-ce 2.5.7) — takes a minute.

Each computer keeps its own characters in `data/saves/`.

## Hosting (one person)

1. Pick your character, then on the map screen choose the map and the Difficulty (1pp–8pp).
2. Press **L** = host on the home network. (H hosts for this computer only.)
3. The first time, the computer asks whether Python may accept incoming connections — click **Allow**
   (macOS) / **Allow access** on Private networks (Windows).
4. The top-right of your screen shows `Hosting on LAN 192.168.x.y · 1/4`.

## Joining (everyone else)

1. Pick your character, then on the map screen press **J**.
2. The Join screen searches this computer and your home network (a few seconds) and lists games like
   `Quinn (Lv 7) - Northshire (8pp) (LAN 192.168.1.23) · 1/4 players`. Pick one and press Enter.
3. Not found? Make sure both computers are on the same Wi-Fi (not a "guest" network), press **R** to search
   again, or press **T** and type the address shown on the host's screen.

## Good to know

- Up to 4 players. Everyone gets XP and quest credit for every kill; each player saves their own progress.
- If the host quits, joiners are put back on the menu (their progress is saved).
- Who can join: anyone on the same home network who finds the game — there is no approval step (chosen on
  purpose for family play). The game can't be reached from the internet, and it only listens while someone is
  hosting with L.
