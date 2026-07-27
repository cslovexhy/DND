# Project Principles

## 1. Research First, Build Second
Always gather ALL available information before implementing. No coding until we have complete data for the feature being built. This means:
- Scrape/download all card stats before coding monster AI
- Get all hero abilities before implementing the ability system
- Understand full adventure structure before building dungeon generation
- Gather all item/treasure data before building the loot system

## 2. Verifiable by AI
All game logic must be testable headlessly via CLI. The game engine runs independently of rendering — we can verify behaviors by running `python3 test.py` without a GUI.

## 3. Free Tools Only
No paid engines, assets, or services. Everything must be CC0/MIT/free.

## 4. Faithful to Source
We're adapting Wrath of Ashardalon (and the D&D Adventure System). Stats, abilities, monsters, and adventures should match the board game as closely as the real-time format allows. We translate, not reinvent.

## 5. Iterative Polish
Get it working first (ugly is fine), then make it look/feel good. Gameplay correctness > visual polish.
