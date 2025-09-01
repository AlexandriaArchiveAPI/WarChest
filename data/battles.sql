-- WarChest schema (SQLite-ready). Works on Postgres too (minor syntax differences).
PRAGMA foreign_keys = ON;

-- ---------- Tables ----------
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
  year           TEXT,               -- keep as TEXT to allow BCE/CE, ranges
  date_exact     TEXT,               -- optional "YYYY-MM-DD" or textual
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

-- side: 'A' or 'B' (two main sides keeps it simple; extend if needed)
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

-- ---------- Seed data: Wars ----------
INSERT OR IGNORE INTO wars (id, name, dates, locations, result, significance) VALUES
  (1, 'Greco-Persian Wars', '499–449 BCE', 'Greece, Anatolia, Aegean', 'Greek defensive success', 'Preserved independence of Greek states; shaped Western history'),
  (2, 'Norman Conquest of England', '1066–1071 CE', 'England', 'Norman victory', 'Transformation of English language, law, and aristocracy'),
  (3, 'Hundred Years'' War', '1337–1453 CE', 'France, Low Countries, England', 'French victory', 'Rise of national identities; decline of feudalism');

-- ---------- Seed data: Battles ----------
INSERT OR IGNORE INTO battles (id, war_id, name, year, date_exact, location, strength_notes, outcome, significance) VALUES
  (101, 1, 'Battle of Thermopylae', '480 BCE', NULL, 'Thermopylae, Greece',
   '~7,000 Greeks vs. ~100,000–150,000 Persians (est.)', 'Persian victory',
   'Symbol of heroic resistance against overwhelming odds'),
  (102, 2, 'Battle of Hastings', '1066 CE', '1066-10-14', 'Near Hastings, England',
   '~7,000 each side', 'Norman victory',
   'Beginning of Norman rule in England'),
  (103, 3, 'Battle of Agincourt', '1415 CE', '1415-10-25', 'Northern France',
   '~6,000 English vs. ~20,000 French (est.)', 'English victory',
   'Showcase of longbow effectiveness; major morale boost');

-- ---------- Seed data: Belligerents ----------
INSERT OR IGNORE INTO belligerents (id, name) VALUES
  (1, 'Greek city-states'),
  (2, 'Achaemenid Persia'),
  (3, 'Normans'),
  (4, 'Anglo-Saxons'),
  (5, 'England'),
  (6, 'France');

-- ---------- Battle ↔ Belligerents ----------
INSERT OR IGNORE INTO battle_belligerents (battle_id, belligerent_id, side) VALUES
  -- Thermopylae
  (101, 1, 'A'), (101, 2, 'B'),
  -- Hastings
  (102, 3, 'A'), (102, 4, 'B'),
  -- Agincourt
  (103, 5, 'A'), (103, 6, 'B');

-- ---------- Seed data: Commanders ----------
INSERT OR IGNORE INTO commanders (id, name) VALUES
  (1, 'Leonidas I'),
  (2, 'Xerxes I'),
  (3, 'William of Normandy'),
  (4, 'Harold II'),
  (5, 'Henry V of England'),
  (6, 'Charles d''Albret');

-- ---------- Battle ↔ Commanders ----------
INSERT OR IGNORE INTO battle_commanders (battle_id, commander_id, side, role) VALUES
  -- Thermopylae
  (101, 1, 'A', 'Spartan king'),   -- Leonidas
  (101, 2, 'B', 'Great King'),     -- Xerxes
  -- Hastings
  (102, 3, 'A', 'Duke of Normandy'),
  (102, 4, 'B', 'King of England'),
  -- Agincourt
  (103, 5, 'A', 'King of England'),
  (103, 6, 'B', 'Constable of France');

-- ---------- Helpful Views ----------
CREATE VIEW IF NOT EXISTS battle_overview AS
SELECT
  b.id,
  b.name AS battle,
  b.year,
  b.date_exact,
  b.location,
  w.name AS war,
  b.outcome,
  b.significance
FROM battles b
LEFT JOIN wars w ON w.id = b.war_id;

CREATE VIEW IF NOT EXISTS battle_sides AS
SELECT
  b.name AS battle,
  bb.side,
  GROUP_CONCAT(be.name, ', ') AS belligerents
FROM battles b
JOIN battle_belligerents bb ON bb.battle_id = b.id
JOIN belligerents be ON be.id = bb.belligerent_id
GROUP BY b.id, bb.side;

-- ---------- Example queries (uncomment to test in sqlite3) ----------
-- .headers on
-- .mode column
-- SELECT * FROM battle_overview;
-- SELECT * FROM battle_sides WHERE battle = 'Battle of Hastings';
