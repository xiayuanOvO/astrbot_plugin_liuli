CREATE_PROFILES_TABLE = """CREATE TABLE IF NOT EXISTS profiles (
    scope TEXT NOT NULL,
    platform_id TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    data_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (scope, platform_id, entity_id)
)"""

CREATE_CURRENCY_ACCOUNTS_TABLE = """CREATE TABLE IF NOT EXISTS currency_accounts (
    platform_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (platform_id, player_id)
)"""

CREATE_CURRENCY_TRANSACTIONS_TABLE = """CREATE TABLE IF NOT EXISTS currency_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    amount INTEGER NOT NULL CHECK (amount != 0),
    reason TEXT NOT NULL,
    idempotency_key TEXT UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)"""

CREATE_CURRENCY_TRANSACTION_PLAYER_INDEX = """CREATE INDEX IF NOT EXISTS
    idx_currency_transactions_player
    ON currency_transactions(platform_id, player_id, id)"""

CREATE_PETS_TABLE = """CREATE TABLE IF NOT EXISTS pets (
    pet_id TEXT PRIMARY KEY,
    platform_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    species_id TEXT NOT NULL,
    name TEXT NOT NULL,
    level INTEGER NOT NULL DEFAULT 1 CHECK (level BETWEEN 1 AND 100),
    experience INTEGER NOT NULL DEFAULT 0 CHECK (experience >= 0),
    current_hp INTEGER NOT NULL CHECK (current_hp >= 0),
    current_mp INTEGER NOT NULL CHECK (current_mp >= 0),
    is_active INTEGER NOT NULL DEFAULT 0 CHECK (is_active IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)"""

CREATE_PET_OWNER_INDEX = """CREATE INDEX IF NOT EXISTS idx_pets_owner
    ON pets(platform_id, player_id, created_at)"""

CREATE_ONE_ACTIVE_PET_INDEX = """CREATE UNIQUE INDEX IF NOT EXISTS
    idx_pets_one_active_per_owner ON pets(platform_id, player_id)
    WHERE is_active = 1"""

CREATE_PET_SKILLS_TABLE = """CREATE TABLE IF NOT EXISTS pet_skills (
    pet_id TEXT NOT NULL REFERENCES pets(pet_id) ON DELETE CASCADE,
    skill_id TEXT NOT NULL,
    learned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    slot INTEGER CHECK (slot BETWEEN 1 AND 4),
    PRIMARY KEY (pet_id, skill_id),
    UNIQUE (pet_id, slot)
)"""

CREATE_SPIRIT_BATTLES_TABLE = """CREATE TABLE IF NOT EXISTS spirit_battles (
    battle_id TEXT PRIMARY KEY,
    platform_id TEXT NOT NULL,
    group_id TEXT NOT NULL,
    challenger_id TEXT NOT NULL,
    opponent_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('pending', 'active', 'finished', 'declined', 'expired', 'forfeit', 'draw')),
    current_turn_player_id TEXT,
    round_number INTEGER NOT NULL DEFAULT 0 CHECK (round_number >= 0),
    state_json TEXT NOT NULL,
    winner_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
)"""

CREATE_SPIRIT_BATTLE_PLAYER_INDEX = """CREATE INDEX IF NOT EXISTS
    idx_spirit_battles_player_state ON spirit_battles(platform_id, challenger_id, opponent_id, state)"""

CREATE_SPIRIT_BATTLE_GROUP_INDEX = """CREATE INDEX IF NOT EXISTS
    idx_spirit_battles_group_state ON spirit_battles(platform_id, group_id, state, created_at)"""

CREATE_SPIRIT_BATTLE_ACTIONS_TABLE = """CREATE TABLE IF NOT EXISTS spirit_battle_actions (
    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
    battle_id TEXT NOT NULL REFERENCES spirit_battles(battle_id) ON DELETE CASCADE,
    round_number INTEGER NOT NULL,
    player_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    skill_id TEXT,
    result_json TEXT NOT NULL,
    state_before_json TEXT NOT NULL,
    state_after_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (battle_id, round_number, player_id)
)"""

CREATE_SPIRIT_BATTLE_ACTIONS_INDEX = """CREATE INDEX IF NOT EXISTS
    idx_spirit_battle_actions_battle ON spirit_battle_actions(battle_id, action_id)"""

CREATE_DUNGEON_RUNS_TABLE = """CREATE TABLE IF NOT EXISTS dungeon_runs (
    run_id TEXT PRIMARY KEY,
    platform_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    dungeon_id TEXT NOT NULL,
    difficulty_id TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('active', 'completed', 'defeated', 'retreated')),
    state_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
)"""

CREATE_DUNGEON_RUN_ACTIVE_INDEX = """CREATE UNIQUE INDEX IF NOT EXISTS
    idx_dungeon_runs_one_active_per_player ON dungeon_runs(platform_id, player_id)
    WHERE state='active'"""

CREATE_DUNGEON_PROGRESS_TABLE = """CREATE TABLE IF NOT EXISTS dungeon_progress (
    platform_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    dungeon_id TEXT NOT NULL,
    difficulty_id TEXT NOT NULL,
    clear_count INTEGER NOT NULL DEFAULT 0 CHECK (clear_count >= 0),
    first_cleared_at TEXT,
    PRIMARY KEY (platform_id, player_id, dungeon_id, difficulty_id)
)"""

CREATE_DUNGEON_PLAYER_STATE_TABLE = """CREATE TABLE IF NOT EXISTS dungeon_player_state (
    platform_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    current_city_id TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (platform_id, player_id)
)"""

CREATE_DUNGEON_RUN_EVENTS_TABLE = """CREATE TABLE IF NOT EXISTS dungeon_run_events (
    run_id TEXT NOT NULL REFERENCES dungeon_runs(run_id) ON DELETE CASCADE,
    event_index INTEGER NOT NULL,
    event_id TEXT NOT NULL,
    outcome_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, event_index)
)"""

CREATE_DUNGEON_ACTIONS_TABLE = """CREATE TABLE IF NOT EXISTS dungeon_actions (
    action_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES dungeon_runs(run_id) ON DELETE CASCADE,
    event_index INTEGER NOT NULL,
    round_number INTEGER NOT NULL,
    actor_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    skill_id TEXT,
    request_key TEXT UNIQUE,
    result_json TEXT NOT NULL,
    state_before_json TEXT NOT NULL,
    state_after_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE (run_id, event_index, round_number, actor_id)
)"""
