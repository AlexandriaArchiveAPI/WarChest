#!/usr/bin/env python3
"""
WarChest data ingester.
- Creates SQLite DB + schema (if missing)
- Loads wars.csv, battles.csv, battles.json (if present)
- Upserts wars, battles, belligerents, commanders, and join tables

Usage:
  python scripts/ingest.py --db data/warchest.db --data data/
"""
from __future__ import annotations
import argparse, csv, json, sqlite3, sys
from pathlib import Path

SCHEMA_SQL = r"""
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS wars (
  id            INTEGER PRIMARY KEY,
  name          TEXT NOT NULL UNIQUE,
  dates         TEXT,
  locations     TEXT,
  result        TEXT,
  significance  TEXT
);

CREATE TABLE IF NOT EXISTS battles (
  id             INTEGER PRIMARY KEY,
  war_id         INTEGER REFERENCES wars(id) ON DELETE SET NULL,
  name           TEXT NOT NULL,
  year           TEXT,
  date_exact     TEXT,
  location       TEXT,
  strength_notes TEXT,
  outcome        TEXT,
  significance   TEXT,
  UNIQUE(name, year)
);

CREATE TABLE IF NOT EXISTS belligerents (
  id    INTEGER PRIMARY KEY,
  name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS battle_belligerents (
  battle_id      INTEGER NOT NULL REFERENCES battles(id) ON DELETE CASCADE,
  belligerent_id INTEGER NOT NULL REFERENCES belligerents(id) ON DELETE CASCADE,
  side           TEXT NOT NULL CHECK(side IN ('A','B')),
  PRIMARY KEY (battle_id, belligerent_id)
);

CREATE TABLE IF NOT EXISTS commanders (
  id    INTEGER PRIMARY KEY,
  name  TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS battle_commanders (
  battle_id    INTEGER NOT NULL REFERENCES battles(id) ON DELETE CASCADE,
  commander_id INTEGER NOT NULL REFERENCES commanders(id) ON DELETE CASCADE,
  side         TEXT NOT NULL CHECK(side IN ('A','B')),
  role         TEXT,
  PRIMARY KEY (battle_id, commander_id)
);
"""

def connect(db_path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA foreign_keys = ON;")
    return con

def init_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA_SQL)
    con.commit()

# --- helpers ---------------------------------------------------------------

def upsert_war(con, name, dates=None, locations=None, result=None, significance=None):
    cur = con.execute("SELECT id FROM wars WHERE name = ?", (name,))
    row = cur.fetchone()
    if row:
        war_id = row[0]
        con.execute("""UPDATE wars SET dates=COALESCE(?,dates),
                                     locations=COALESCE(?,locations),
                                     result=COALESCE(?,result),
                                     significance=COALESCE(?,significance)
                       WHERE id=?""", (dates, locations, result, significance, war_id))
        return war_id
    cur = con.execute("""INSERT INTO wars(name, dates, locations, result, significance)
                         VALUES(?,?,?,?,?)""", (name, dates, locations, result, significance))
    return cur.lastrowid

def upsert_belligerent(con, name):
    name = name.strip()
    if not name: return None
    cur = con.execute("SELECT id FROM belligerents WHERE name = ?", (name,))
    row = cur.fetchone()
    if row: return row[0]
    cur = con.execute("INSERT INTO belligerents(name) VALUES(?)", (name,))
    return cur.lastrowid

def upsert_commander(con, name):
    name = name.strip()
    if not name: return None
    cur = con.execute("SELECT id FROM commanders WHERE name = ?", (name,))
    row = cur.fetchone()
    if row: return row[0]
    cur = con.execute("INSERT INTO commanders(name) VALUES(?)", (name,))
    return cur.lastrowid

def upsert_battle(con, name, year, war_name=None, date_exact=None,
                  location=None, strength=None, outcome=None, significance=None):
    war_id = None
    if war_name:
        war_id = upsert_war(con, war_name)

    # Try find existing
    cur = con.execute("SELECT id FROM battles WHERE name=? AND year=?", (name, year))
    row = cur.fetchone()
    if row:
        battle_id = row[0]
        con.execute("""UPDATE battles SET war_id=COALESCE(?, war_id),
                                         date_exact=COALESCE(?, date_exact),
                                         location=COALESCE(?, location),
                                         strength_notes=COALESCE(?, strength_notes),
                                         outcome=COALESCE(?, outcome),
                                         significance=COALESCE(?, significance)
                       WHERE id=?""",
                    (war_id, date_exact, location, strength, outcome, significance, battle_id))
        return battle_id

    cur = con.execute("""INSERT INTO battles(war_id, name, year, date_exact, location,
                                             strength_notes, outcome, significance)
                         VALUES(?,?,?,?,?,?,?,?)""",
                      (war_id, name, year, date_exact, location, strength, outcome, significance))
    return cur.lastrowid

def link_battle_belligerents(con, battle_id, side, names):
    for nm in names:
        if not nm.strip(): continue
        bel_id = upsert_belligerent(con, nm)
        con.execute("""INSERT OR IGNORE INTO battle_belligerents(battle_id, belligerent_id, side)
                       VALUES(?,?,?)""", (battle_id, bel_id, side))

def link_battle_commanders(con, battle_id, side, names):
    for nm in names:
        if not nm.strip(): continue
        cmd_id = upsert_commander(con, nm)
        con.execute("""INSERT OR IGNORE INTO battle_commanders(battle_id, commander_id, side, role)
                       VALUES(?,?,?,NULL)""", (battle_id, cmd_id, side))

# --- ingestion -------------------------------------------------------------

def parse_belligerents_field(s: str):
    """
    Accepts formats:
      "Side A vs. Side B"
      "A; A2 vs. B; B2"
    Returns (listA, listB)
    """
    if not s: return [], []
    parts = [p.strip() for p in s.split(" vs. ")]
    if len(parts) != 2:
        # fallback: try 'vs' without dot
        parts = [p.strip() for p in s.split(" vs ")]
        if len(parts) != 2:
            return [s], []
    A = [x.strip() for x in parts[0].split(";")]
    B = [x.strip() for x in parts[1].split(";")]
    return A, B

def parse_commanders_field(s: str):
    """
    Accepts "Name A; Name B" OR "Name A vs. Name B"
    Returns (listA, listB) when 'vs.' present; otherwise returns (list, [])
    """
    if not s: return [], []
    if " vs" in s:
        A, B = [p.strip() for p in s.split(" vs")][0], s.split(" vs")[-1]
        return [x.strip() for x in A.split(";")], [x.strip() for x in B.split(";")]
    return [x.strip() for x in s.split(";")], []

def load_wars_csv(con, path: Path):
    if not path.exists(): return
    with path.open(newline='', encoding="utf-8") as f:
        for row in csv.DictReader(f):
            upsert_war(con,
                       name=row.get("Name"),
                       dates=row.get("Dates"),
                       locations=row.get("Location(s)") or row.get("Locations"),
                       result=row.get("Result"),
                       significance=row.get("Significance"))
    con.commit()

def load_battles_csv(con, path: Path):
    if not path.exists(): return
    with path.open(newline='', encoding="utf-8") as f:
        for row in csv.DictReader(f):
            battle_id = upsert_battle(
                con,
                name=row.get("Name"),
                year=row.get("Year"),
                war_name=row.get("War/Campaign") or row.get("War"),
                date_exact=None,
                location=row.get("Location"),
                strength=row.get("Strength"),
                outcome=row.get("Outcome"),
                significance=row.get("Significance"),
            )
            A, B = parse_belligerents_field(row.get("Belligerents", ""))
            link_battle_belligerents(con, battle_id, 'A', A)
            link_battle_belligerents(con, battle_id, 'B', B)

            # Commanders may be "A; B" or "A vs. B"
            cA, cB = parse_commanders_field(row.get("Commanders", ""))
            if cB:  # vs format
                link_battle_commanders(con, battle_id, 'A', cA)
                link_battle_commanders(con, battle_id, 'B', cB)
            else:
                # no sides given; attach as 'A'
                link_battle_commanders(con, battle_id, 'A', cA)
    con.commit()

def load_battles_json(con, path: Path):
    if not path.exists(): return
    data = json.loads(path.read_text(encoding="utf-8"))
    for rec in data:
        battle_id = upsert_battle(
            con,
            name=rec.get("name"),
            year=rec.get("year"),
            war_name=rec.get("war"),
            date_exact=rec.get("date_exact"),
            location=rec.get("location"),
            strength=rec.get("strength"),
            outcome=rec.get("outcome"),
            significance=rec.get("significance"),
        )
        # belligerents
        bells = rec.get("belligerents", [])
        if isinstance(bells, dict):
            link_battle_belligerents(con, battle_id, 'A', bells.get("A", []))
            link_battle_belligerents(con, battle_id, 'B', bells.get("B", []))
        else:
            # assume two entries
            A = [bells[0]] if bells else []
            B = [bells[1]] if len(bells) > 1 else []
            link_battle_belligerents(con, battle_id, 'A', A)
            link_battle_belligerents(con, battle_id, 'B', B)

        # commanders
        cmds = rec.get("commanders", [])
        if isinstance(cmds, dict):
            link_battle_commanders(con, battle_id, 'A', cmds.get("A", []))
            link_battle_commanders(con, battle_id, 'B', cmds.get("B", []))
        else:
            link_battle_commanders(con, battle_id, 'A', cmds)
    con.commit()

def main():
    ap = argparse.ArgumentParser(description="Ingest WarChest CSV/JSON into SQLite")
    ap.add_argument("--db", default="data/warchest.db", type=Path)
    ap.add_argument("--data", default="data", type=Path, help="folder containing CSV/JSON")
    args = ap.parse_args()

    args.db.parent.mkdir(parents=True, exist_ok=True)
    con = connect(args.db)
    try:
        init_schema(con)
        load_wars_csv(con, args.data / "wars.csv")
        load_battles_csv(con, args.data / "battles.csv")
        load_battles_json(con, args.data / "battles.json")
        print("✔ Ingest complete →", args.db)
    except Exception as e:
        con.rollback()
        print("Error:", e, file=sys.stderr)
        sys.exit(1)
    finally:
        con.close()

if __name__ == "__main__":
    main()
