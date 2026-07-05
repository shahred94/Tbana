"""SQLite storage for TBana Stream."""

import json
import re
import sqlite3

from pathlib import Path
from contextlib import closing

from app.core.paths import data_path

DATABASE_PATH = (
    data_path("livetrigger.db")
)


def get_connection() -> sqlite3.Connection:
    """Create SQLite connection."""

    connection = sqlite3.connect(
        DATABASE_PATH
    )

    connection.row_factory = (
        sqlite3.Row
    )

    connection.execute(
        "PRAGMA foreign_keys = ON"
    )

    return connection


def normalize_action_type(
    action_type: str | None,
) -> str | None:
    """Normalize action types while accepting legacy labels."""

    if action_type is None:

        return None

    value = re.sub(
        r"\s+",
        " ",
        action_type.strip(),
    ).upper()

    if value in {
        "NOTE",
        "EFFECT NOTE",
        "EFFECT",
        "EFFECT_NOTE",
        "EFFECT-NOTE",
    }:

        return "NOTE"

    return value


def normalize_gift_name(
    gift_name: str | None,
) -> str:
    """Normalize gift names for stable matching."""

    value = re.sub(
        r"\s+",
        " ",
        str(gift_name or "").strip(),
    ).casefold()

    return re.sub(
        r"[^a-z0-9]+",
        "",
        value,
    )


def normalize_all_action_types() -> None:
    """Convert legacy action type labels to canonical values."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            UPDATE events
            SET action_type = UPPER(TRIM(action_type))
            WHERE action_type IS NOT NULL
            """
        )

        connection.execute(
            """
            UPDATE event_actions
            SET action_type = UPPER(TRIM(action_type))
            WHERE action_type IS NOT NULL
            """
        )

        connection.execute(
            """
            UPDATE events
            SET action_type = 'NOTE'
            WHERE UPPER(TRIM(action_type)) IN
            (
                'EFFECT NOTE',
                'EFFECT',
                'EFFECT_NOTE',
                'EFFECT-NOTE'
            )
            """
        )

        connection.execute(
            """
            UPDATE event_actions
            SET action_type = 'NOTE'
            WHERE UPPER(TRIM(action_type)) IN
            (
                'EFFECT NOTE',
                'EFFECT',
                'EFFECT_NOTE',
                'EFFECT-NOTE'
            )
            """
        )

        connection.commit()


def migrate_legacy_events_to_event_triggers(
    cursor: sqlite3.Cursor,
) -> int:
    """Copy old events/event_actions rows into the unified event trigger system."""

    cursor.execute(
        """
        SELECT
            id,
            enabled,
            trigger_type,
            trigger_value,
            user_filter,
            action_type,
            action_value
        FROM events
        ORDER BY id
        """
    )
    legacy_events = cursor.fetchall()

    if not legacy_events:

        return 0

    cursor.execute(
        """
        SELECT
            trigger_type,
            trigger_value,
            user_filter
        FROM event_triggers
        """
    )
    existing_triggers = {
        (
            str(row["trigger_type"] or "").strip().casefold(),
            str(row["trigger_value"] or "").strip().casefold(),
            str(row["user_filter"] or "ANY").strip().casefold(),
        )
        for row in cursor.fetchall()
    }

    migrated = 0

    for event in legacy_events:

        trigger_type = str(
            event["trigger_type"] or "GIFT"
        ).strip()
        trigger_value = str(
            event["trigger_value"] or ""
        ).strip()
        user_filter = str(
            event["user_filter"] or "ANY"
        ).strip() or "ANY"

        trigger_key = (
            trigger_type.casefold(),
            trigger_value.casefold(),
            user_filter.casefold(),
        )

        if trigger_key in existing_triggers:

            continue

        cursor.execute(
            """
            SELECT
                action_type,
                action_value
            FROM event_actions
            WHERE event_id = ?
            ORDER BY id
            """,
            (event["id"],),
        )
        legacy_actions = cursor.fetchall()

        if not legacy_actions and (
            event["action_type"] is not None
            and event["action_value"] is not None
        ):

            legacy_actions = [
                {
                    "action_type": event["action_type"],
                    "action_value": event["action_value"],
                }
            ]

        normalized_actions = []

        for action in legacy_actions:

            action_type = normalize_action_type(
                action["action_type"]
            )
            action_value = action["action_value"]

            if (
                not action_type
                or action_value is None
            ):

                continue

            normalized_actions.append(
                (
                    action_type,
                    str(action_value),
                )
            )

        if not normalized_actions:

            continue

        action_name = (
            f"Legacy {trigger_type} {trigger_value}"
        ).strip()

        cursor.execute(
            """
            INSERT INTO action_presets
            (
                name,
                duration,
                description,
                enabled,
                media_volume,
                overlay_screen,
                global_cooldown,
                user_cooldown,
                fade_enabled,
                repeat_gift_combos,
                skip_on_next_action
            )
            VALUES
            (?, 0, ?, ?, 100, 1, 0, 0, 0, 0, 0)
            """,
            (
                action_name,
                "Migrated from legacy events table",
                int(bool(event["enabled"])),
            ),
        )
        action_id = cursor.lastrowid

        for index, (action_type, action_value) in enumerate(
            normalized_actions,
            start=1,
        ):

            cursor.execute(
                """
                INSERT INTO action_steps
                (
                    action_id,
                    step_order,
                    step_type,
                    step_value
                )
                VALUES
                (?, ?, ?, ?)
                """,
                (
                    action_id,
                    index,
                    action_type,
                    action_value,
                ),
            )

        cursor.execute(
            """
            INSERT INTO event_triggers
            (
                enabled,
                trigger_type,
                trigger_value,
                user_filter,
                action_id,
                action_mode,
                action_group
            )
            VALUES
            (?, ?, ?, ?, ?, 'single', '')
            """,
            (
                int(bool(event["enabled"])),
                trigger_type,
                trigger_value,
                user_filter,
                action_id,
            ),
        )

        existing_triggers.add(trigger_key)
        migrated += 1

    return migrated



def initialize_database() -> None:
    """Create database tables."""

    with closing(get_connection()) as connection:

        cursor = connection.cursor()


        # Legacy Gift Rules
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS gift_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                gift_name TEXT NOT NULL,

                sound_file TEXT NOT NULL
            )
            """
        )


        # Event Engine
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                enabled INTEGER DEFAULT 1,

                trigger_type TEXT NOT NULL,

                trigger_value TEXT NOT NULL,

                user_filter TEXT
                DEFAULT 'ANY',

                action_type TEXT,

                action_value TEXT
            )
            """
        )


        # Multiple Actions
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS event_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                event_id INTEGER NOT NULL,

                action_type TEXT NOT NULL,

                action_value TEXT NOT NULL,

                FOREIGN KEY (event_id)
                REFERENCES events(id)
                ON DELETE CASCADE
            )
            """
        )
        # ==========================================
        # TBana Stream V2 - Action Library
        # ==========================================


        # Action Presets
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS action_presets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                name TEXT NOT NULL,

                duration INTEGER DEFAULT 0,

                description TEXT DEFAULT "",

                enabled INTEGER DEFAULT 1,

                media_volume INTEGER DEFAULT 100,

                overlay_screen INTEGER DEFAULT 1,

                global_cooldown INTEGER DEFAULT 0,

                user_cooldown INTEGER DEFAULT 0,

                fade_enabled INTEGER DEFAULT 0,

                repeat_gift_combos INTEGER DEFAULT 0,

                skip_on_next_action INTEGER DEFAULT 0
            )
            """
        )

        for statement in (
            "ALTER TABLE action_presets "
            "ADD COLUMN media_volume INTEGER DEFAULT 100",
            "ALTER TABLE action_presets "
            "ADD COLUMN overlay_screen INTEGER DEFAULT 1",
            "ALTER TABLE action_presets "
            "ADD COLUMN global_cooldown INTEGER DEFAULT 0",
            "ALTER TABLE action_presets "
            "ADD COLUMN user_cooldown INTEGER DEFAULT 0",
            "ALTER TABLE action_presets "
            "ADD COLUMN fade_enabled INTEGER DEFAULT 0",
            "ALTER TABLE action_presets "
            "ADD COLUMN repeat_gift_combos INTEGER DEFAULT 0",
            "ALTER TABLE action_presets "
            "ADD COLUMN skip_on_next_action INTEGER DEFAULT 0",
        ):

            try:

                cursor.execute(
                    statement
                )

            except sqlite3.OperationalError:

                pass


        # Action Steps
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS action_steps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                action_id INTEGER NOT NULL,

                step_order INTEGER DEFAULT 0,

                step_type TEXT NOT NULL,

                step_value TEXT NOT NULL,

                FOREIGN KEY (action_id)
                REFERENCES action_presets(id)
                ON DELETE CASCADE
            )
            """
        )


        # Event Trigger Mapping
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS event_triggers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                enabled INTEGER DEFAULT 1,

                trigger_type TEXT NOT NULL,

                trigger_value TEXT NOT NULL,

                user_filter TEXT DEFAULT 'ANY',

                action_id INTEGER NOT NULL,

                action_mode TEXT DEFAULT 'single',

                action_group TEXT DEFAULT '',

                FOREIGN KEY (action_id)
                REFERENCES action_presets(id)
                ON DELETE CASCADE
            )
            """
        )

        for statement in (
            "ALTER TABLE event_triggers "
            "ADD COLUMN action_mode TEXT DEFAULT 'single'",
            "ALTER TABLE event_triggers "
            "ADD COLUMN action_group TEXT DEFAULT ''",
        ):

            try:

                cursor.execute(
                    statement
                )

            except sqlite3.OperationalError:

                pass
        
        # Settings
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,

                key TEXT UNIQUE NOT NULL,

                value TEXT
    )
    """
)


        # Default Event
        cursor.execute(
            """
            INSERT OR IGNORE INTO events
            (
                id,

                trigger_type,

                trigger_value,

                action_type,

                action_value
            )
            VALUES
            (
                1,

                'GIFT',

                'Rose',

                'SOUND',

                'rose.mp3'
            )
            """
        )


        # Migration:
        # Old event action
        # -> event_actions
        cursor.execute(
            """
            INSERT INTO event_actions
            (
                event_id,

                action_type,

                action_value
            )
            SELECT

                id,

                action_type,

                action_value

            FROM events

            WHERE

                action_type IS NOT NULL

                AND action_value IS NOT NULL

                AND NOT EXISTS
                (
                    SELECT 1

                    FROM event_actions

                    WHERE
                    event_actions.event_id
                    = events.id
                )
            """
        )

        migrate_legacy_events_to_event_triggers(
            cursor
        )


        connection.commit()

    normalize_all_action_types()


def get_all_gift_rules() -> list[dict]:
    """Backward compatibility for old API."""

    return get_gift_rules()



def get_gift_rules() -> list[dict]:
    """Get all gift rules."""

    with closing(get_connection()) as connection:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                event_triggers.id,
                event_triggers.enabled,
                event_triggers.trigger_value,
                event_triggers.action_id,
                (
                    SELECT action_steps.step_value
                    FROM action_steps
                    WHERE
                        action_steps.action_id = action_presets.id
                        AND LOWER(action_steps.step_type) = 'sound'
                    ORDER BY
                        action_steps.step_order,
                        action_steps.id
                    LIMIT 1
                ) AS sound_file,
                (
                    SELECT action_steps.step_value
                    FROM action_steps
                    WHERE
                        action_steps.action_id = action_presets.id
                        AND LOWER(action_steps.step_type) = 'overlay'
                    ORDER BY
                        action_steps.step_order,
                        action_steps.id
                    LIMIT 1
                ) AS overlay_name
            FROM event_triggers
            LEFT JOIN action_presets
                ON event_triggers.action_id = action_presets.id
            WHERE
                LOWER(event_triggers.trigger_type) = 'gift'
            ORDER BY
                event_triggers.id
            """
        )

        rows = cursor.fetchall()

        return [
            {
                "id": row["id"],
                "enabled": bool(row["enabled"]),
                "gift_name": row["trigger_value"],
                "sound": row["sound_file"] or "",
                "sound_file": row["sound_file"] or "",
                "overlay": row["overlay_name"] or "",
            }
            for row in rows
        ]



def get_gift_rule(
    gift_name: str,
) -> dict | None:
    """Get a single gift rule."""

    normalized_gift_name = normalize_gift_name(
        gift_name
    )

    with closing(get_connection()) as connection:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                event_triggers.id,
                event_triggers.enabled,
                event_triggers.trigger_value,
                event_triggers.action_id,
                (
                    SELECT action_steps.step_value
                    FROM action_steps
                    WHERE
                        action_steps.action_id = action_presets.id
                        AND LOWER(action_steps.step_type) = 'sound'
                    ORDER BY
                        action_steps.step_order,
                        action_steps.id
                    LIMIT 1
                ) AS sound_file,
                (
                    SELECT action_steps.step_value
                    FROM action_steps
                    WHERE
                        action_steps.action_id = action_presets.id
                        AND LOWER(action_steps.step_type) = 'overlay'
                    ORDER BY
                        action_steps.step_order,
                        action_steps.id
                    LIMIT 1
                ) AS overlay_name
            FROM event_triggers
            LEFT JOIN action_presets
                ON event_triggers.action_id = action_presets.id
            WHERE
                LOWER(event_triggers.trigger_type) = 'gift'
            ORDER BY
                event_triggers.id
            """
        )

        row = None

        for candidate in cursor.fetchall():

            if (
                normalize_gift_name(
                    candidate["trigger_value"]
                )
                ==
                normalized_gift_name
            ):

                row = candidate
                break

        if row is None:

            return None

        return {
            "id": row["id"],
            "enabled": bool(row["enabled"]),
            "gift_name": row["trigger_value"],
            "sound": row["sound_file"] or "",
            "sound_file": row["sound_file"] or "",
            "overlay": row["overlay_name"] or "",
            "action_id": row["action_id"],
        }



def add_gift_rule(
    gift_name: str,
    sound_file: str,
    overlay: str = "",
) -> None:
    """Add a gift rule."""

    with closing(get_connection()) as connection:

        cursor = connection.execute(
            """
            INSERT INTO action_presets
            (
                name,
                duration,
                description,
                media_volume,
                overlay_screen,
                global_cooldown,
                user_cooldown,
                fade_enabled,
                repeat_gift_combos,
                skip_on_next_action
            )
            VALUES
            (?, 0, 'Gift rule', 100, 1, 0, 0, 0, 1, 0)
            """,
            (
                gift_name,
            )
        )

        action_id = cursor.lastrowid

        connection.execute(
            """
            INSERT INTO action_steps
            (
                action_id,
                step_order,
                step_type,
                step_value
            )
            VALUES
            (?, 1, 'sound', ?)
            """,
            (
                action_id,
                sound_file,
            )
        )

        overlay_value = str(overlay or "").strip()
        if overlay_value:

            connection.execute(
                """
                INSERT INTO action_steps
                (
                    action_id,
                    step_order,
                    step_type,
                    step_value
                )
                VALUES
                (?, 2, 'overlay', ?)
                """,
                (
                    action_id,
                    overlay_value,
                )
            )

        connection.execute(
            """
            INSERT INTO event_triggers
            (
                enabled,
                trigger_type,
                trigger_value,
                user_filter,
                action_id,
                action_mode,
                action_group
            )
            VALUES
            (1, 'GIFT', ?, 'ANY', ?, 'single', '')
            """,
            (
                gift_name,
                action_id,
            )
        )

        connection.commit()



def update_gift_rule(
    rule_id: int,
    gift_name: str,
    sound_file: str,
    overlay: str = "",
) -> None:
    """Update a gift rule."""

    with closing(get_connection()) as connection:

        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT action_id
            FROM event_triggers
            WHERE id = ?
            """,
            (
                rule_id,
            )
        )

        row = cursor.fetchone()
        if row is None:
            return

        action_id = row["action_id"]

        connection.execute(
            """
            UPDATE event_triggers
            SET trigger_value = ?
            WHERE id = ?
            """,
            (
                gift_name,
                rule_id,
            )
        )

        connection.execute(
            """
            UPDATE action_presets
            SET name = ?
            WHERE id = ?
            """,
            (
                gift_name,
                action_id,
            )
        )

        connection.execute(
            """
            DELETE FROM action_steps
            WHERE action_id = ?
            """,
            (
                action_id,
            )
        )

        connection.execute(
            """
            INSERT INTO action_steps
            (
                action_id,
                step_order,
                step_type,
                step_value
            )
            VALUES
            (?, 1, 'sound', ?)
            """,
            (
                action_id,
                sound_file,
            )
        )

        overlay_value = str(overlay or "").strip()
        if overlay_value:

            connection.execute(
                """
                INSERT INTO action_steps
                (
                    action_id,
                    step_order,
                    step_type,
                    step_value
                )
                VALUES
                (?, 2, 'overlay', ?)
                """,
                (
                    action_id,
                    overlay_value,
                )
            )

        connection.commit()



def delete_gift_rule(
    rule_id: int,
) -> None:
    """Delete a gift rule."""

    with closing(get_connection()) as connection:

        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT action_id
            FROM event_triggers
            WHERE id = ?
            """,
            (
                rule_id,
            )
        )

        row = cursor.fetchone()
        if row is None:
            return

        action_id = row["action_id"]

        connection.execute(
            """
            DELETE FROM event_triggers
            WHERE id = ?
            """,
            (
                rule_id,
            )
        )

        connection.execute(
            """
            DELETE FROM action_presets
            WHERE id = ?
            """,
            (
                action_id,
            )
        )

        connection.commit()


def update_gift_status(
    rule_id: int,
    enabled: bool,
) -> None:
    """Update a gift rule status."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            UPDATE event_triggers
            SET enabled = ?
            WHERE id = ?
            """,
            (
                int(enabled),
                rule_id,
            )
        )

        connection.commit()


def get_events() -> list[dict]:
    """Get all events."""

    with closing(get_connection()) as connection:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                enabled,
                trigger_type,
                trigger_value,
                user_filter,
                action_type,
                action_value
            FROM events
            ORDER BY id
            """
        )

        rows = cursor.fetchall()

        return [
            {
                "id": row["id"],
                "enabled": bool(
                    row["enabled"]
                ),
                "trigger_type": row["trigger_type"],
                "trigger_value": row["trigger_value"],
                "user_filter": row["user_filter"],
                "action_type": row["action_type"],
                "action_value": row["action_value"],
            }
            for row in rows
        ]



def get_event(
    event_id: int,
) -> dict | None:
    """Get single event."""

    with closing(get_connection()) as connection:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                *
            FROM events
            WHERE
                id = ?
            """,
            (
                event_id,
            )
        )

        row = cursor.fetchone()

        if row is None:

            return None


        return {
            "id": row["id"],
            "enabled": bool(
                row["enabled"]
            ),
            "trigger_type": row["trigger_type"],
            "trigger_value": row["trigger_value"],
            "user_filter": row["user_filter"],
            "action_type": row["action_type"],
            "action_value": row["action_value"],
        }



def add_event(
    trigger_type: str,
    trigger_value: str,
    user_filter: str,
    action_type: str,
    action_value: str,
) -> None:
    """Create new event."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            INSERT INTO events
            (
                trigger_type,
                trigger_value,
                user_filter,
                action_type,
                action_value
            )
            VALUES
            (?, ?, ?, ?, ?)
            """,
            (
                trigger_type,
                trigger_value,
                user_filter,
                normalize_action_type(action_type),
                action_value,
            )
        )

        connection.commit()



def update_event(
    event_id: int,
    trigger_type: str,
    trigger_value: str,
    user_filter: str,
    action_type: str,
    action_value: str,
) -> None:
    """Update event."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            UPDATE events
            SET
                trigger_type = ?,
                trigger_value = ?,
                user_filter = ?,
                action_type = ?,
                action_value = ?
            WHERE
                id = ?
            """,
            (
                trigger_type,
                trigger_value,
                user_filter,
                normalize_action_type(action_type),
                action_value,
                event_id,
            )
        )

        connection.commit()



def update_event_status(
    event_id: int,
    enabled: bool,
) -> None:
    """Enable or disable event."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            UPDATE events
            SET
                enabled = ?
            WHERE
                id = ?
            """,
            (
                int(enabled),
                event_id,
            )
        )

        connection.commit()



def delete_event(
    event_id: int,
) -> None:
    """Delete event."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            DELETE FROM events
            WHERE
                id = ?
            """,
            (
                event_id,
            )
        )

        connection.commit()
def get_event_actions(
    event_id: int,
) -> list[dict]:
    """Get all actions for an event."""

    with closing(get_connection()) as connection:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                action_type,
                action_value
            FROM event_actions
            WHERE
                event_id = ?
            ORDER BY id
            """,
            (
                event_id,
            )
        )

        rows = cursor.fetchall()

        return [
            {
                "id": row["id"],
                "action_type": row["action_type"],
                "action_value": row["action_value"],
            }
            for row in rows
        ]



def add_event_action(
    event_id: int,
    action_type: str,
    action_value: str,
) -> None:
    """Add action to event."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            INSERT INTO event_actions
            (
                event_id,
                action_type,
                action_value
            )
            VALUES
            (?, ?, ?)
            """,
            (
                event_id,
                normalize_action_type(action_type),
                action_value,
            )
        )

        connection.commit()



def update_event_action(
    action_id: int,
    action_type: str,
    action_value: str,
) -> None:
    """Update event action."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            UPDATE event_actions
            SET
                action_type = ?,
                action_value = ?
            WHERE
                id = ?
            """,
            (
                normalize_action_type(action_type),
                action_value,
                action_id,
            )
        )

        connection.commit()



def delete_event_action(
    action_id: int,
) -> None:
    """Delete action from event."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            DELETE FROM event_actions
            WHERE
                id = ?
            """,
            (
                action_id,
            )
        )

        connection.commit()
        
# ==================================================
# Action Presets V2
# ==================================================

def get_action_presets() -> list[dict]:
    """Get all action presets."""

    with closing(get_connection()) as connection:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                name,
                duration,
                description,
                enabled,
                media_volume,
                overlay_screen,
                global_cooldown,
                user_cooldown,
                fade_enabled,
                repeat_gift_combos,
                skip_on_next_action
            FROM action_presets
            ORDER BY id
            """
        )

        rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "name": row[1],
                "duration": row[2],
                "description": row[3],
                "enabled": bool(row[4]),
                "media_volume": row[5],
                "overlay_screen": row[6],
                "global_cooldown": row[7],
                "user_cooldown": row[8],
                "fade_enabled": bool(row[9]),
                "repeat_gift_combos": bool(row[10]),
                "skip_on_next_action": bool(row[11]),
            }
            for row in rows
        ]


def create_action_preset(
    name: str,
    duration: int,
    description: str,
    media_volume: int = 100,
    overlay_screen: int = 1,
    global_cooldown: int = 0,
    user_cooldown: int = 0,
    fade_enabled: bool = False,
    repeat_gift_combos: bool = False,
    skip_on_next_action: bool = False,
) -> int:
    """Create a new action preset."""

    with closing(get_connection()) as connection:

        cursor = connection.execute(
            """
            INSERT INTO action_presets
            (
                name,
                duration,
                description,
                media_volume,
                overlay_screen,
                global_cooldown,
                user_cooldown,
                fade_enabled,
                repeat_gift_combos,
                skip_on_next_action
            )
            VALUES
            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                duration,
                description,
                media_volume,
                overlay_screen,
                global_cooldown,
                user_cooldown,
                int(fade_enabled),
                int(repeat_gift_combos),
                int(skip_on_next_action),
            )
        )

        connection.commit()

        return cursor.lastrowid

def update_action_preset(
    action_id: int,
    name: str,
    duration: int,
    description: str,
    media_volume: int = 100,
    overlay_screen: int = 1,
    global_cooldown: int = 0,
    user_cooldown: int = 0,
    fade_enabled: bool = False,
    repeat_gift_combos: bool = False,
    skip_on_next_action: bool = False,
) -> None:
    """Update action preset."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            UPDATE action_presets
            SET
                name = ?,
                duration = ?,
                description = ?,
                media_volume = ?,
                overlay_screen = ?,
                global_cooldown = ?,
                user_cooldown = ?,
                fade_enabled = ?,
                repeat_gift_combos = ?,
                skip_on_next_action = ?
            WHERE
                id = ?
            """,
            (
                name,
                duration,
                description,
                media_volume,
                overlay_screen,
                global_cooldown,
                user_cooldown,
                int(fade_enabled),
                int(repeat_gift_combos),
                int(skip_on_next_action),
                action_id,
            )
        )

        connection.commit()


def update_action_preset_status(
    action_id: int,
    enabled: bool,
) -> None:
    """Enable or disable an action preset."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            UPDATE action_presets
            SET enabled = ?
            WHERE id = ?
            """,
            (
                int(enabled),
                action_id,
            ),
        )

        connection.commit()


def delete_action_preset(
    action_id: int,
) -> None:
    """Delete action preset."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            DELETE FROM action_presets
            WHERE
                id = ?
            """,
            (
                action_id,
            )
        )

        connection.commit()
# ==================================================
# Settings
# ==================================================

def get_setting(
    key: str,
) -> str | None:
    """Get setting value."""

    with closing(get_connection()) as connection:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT value
            FROM settings
            WHERE key = ?
            """,
            (
                key,
            )
        )

        row = cursor.fetchone()

        if row is None:

            return None

        return row["value"]



def set_setting(
    key: str,
    value: str,
) -> None:
    """Create or update setting."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            INSERT INTO settings
            (
                key,
                value
            )
            VALUES
            (?, ?)
            ON CONFLICT(key)
            DO UPDATE SET
                value = excluded.value
            """,
            (
                key,
                value,
            )
        )

        connection.commit()


def get_settings() -> list[dict]:
    """Get all settings."""

    with closing(get_connection()) as connection:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT key, value
            FROM settings
            ORDER BY key
            """
        )

        rows = cursor.fetchall()

        return [
            {
                "key": row["key"],
                "value": row["value"],
            }
            for row in rows
        ]


def export_configuration() -> dict:
    """Export complete configurable state."""

    legacy_events = []

    for event in get_events():

        actions = get_event_actions(
            event["id"]
        )

        legacy_events.append(
            {
                "trigger_type": event["trigger_type"],
                "trigger_value": event["trigger_value"],
                "user_filter": event["user_filter"],
                "enabled": event["enabled"],
                "actions": actions,
            }
        )

    action_presets = []

    for action in get_action_presets():

        action_presets.append(
            {
                **action,
                "steps": [
                    {
                        "order": step["order"],
                        "type": step["type"],
                        "value": step["value"],
                    }
                    for step in get_action_steps(
                        action["id"]
                    )
                ],
            }
        )

    event_triggers = []

    for event in get_event_triggers():

        event_triggers.append(
            {
                "id": event["id"],
                "enabled": event["enabled"],
                "trigger_type": event["trigger_type"],
                "trigger_value": event["trigger_value"],
                "user_filter": event["user_filter"],
                "action_id": event["action_id"],
                "action_mode": event["action_mode"],
                "action_group": event["action_group"],
            }
        )

    return {
        "application": "TBana Stream",
        "version": "2.0",
        "preset_type": "GTA Chaos",
        "action_presets": action_presets,
        "event_triggers": event_triggers,
        "events": legacy_events,
        "settings": get_settings(),
    }


def import_configuration(
    config: dict,
) -> dict:
    """Replace events/actions/settings from exported configuration."""

    application = config.get(
        "application"
    )

    if (
        application
        and application not in {"TBana Stream", "LiveTrigger"}
    ):

        raise ValueError(
            "This is not a TBana Stream configuration file."
        )

    has_action_presets = (
        "action_presets" in config
    )
    has_event_triggers = (
        "event_triggers" in config
    )
    has_legacy_events = (
        "events" in config
    )
    has_settings = "settings" in config

    action_presets = config.get(
        "action_presets",
        [],
    )
    event_triggers = config.get(
        "event_triggers",
        [],
    )
    legacy_events = config.get(
        "events",
        [],
    )

    settings = config.get(
        "settings",
        [],
    )

    def integer_value(
        value,
        default=0,
    ) -> int:

        try:

            return int(value)

        except (
            TypeError,
            ValueError,
        ):

            return default

    def boolean_value(
        value,
        default=False,
    ) -> int:

        if value is None:

            value = default

        if isinstance(
            value,
            str,
        ):

            return int(
                value.strip().lower()
                in {
                    "1",
                    "true",
                    "yes",
                    "on",
                }
            )

        return int(
            bool(value)
        )

    def required_id(
        value,
        label: str,
    ) -> int:

        record_id = integer_value(
            value
        )

        if record_id <= 0:

            raise ValueError(
                f"{label} has an invalid ID."
            )

        return record_id

    action_steps_imported = 0

    with closing(get_connection()) as connection:

        cursor = connection.cursor()

        if has_event_triggers:

            cursor.execute(
                "DELETE FROM event_triggers"
            )

        if has_action_presets:

            cursor.execute(
                "DELETE FROM action_steps"
            )

            cursor.execute(
                "DELETE FROM action_presets"
            )

            action_ids = set()

            for action in action_presets:

                action_id = required_id(
                    action.get(
                        "id"
                    ),
                    "Action preset",
                )

                if action_id in action_ids:

                    raise ValueError(
                        "The backup contains duplicate action IDs."
                    )

                action_ids.add(
                    action_id
                )

                cursor.execute(
                    """
                    INSERT INTO action_presets
                    (
                        id,
                        name,
                        duration,
                        description,
                        enabled,
                        media_volume,
                        overlay_screen,
                        global_cooldown,
                        user_cooldown,
                        fade_enabled,
                        repeat_gift_combos,
                        skip_on_next_action
                    )
                    VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        action_id,
                        str(
                            action.get(
                                "name",
                                "",
                            )
                        ),
                        integer_value(
                            action.get(
                                "duration"
                            )
                        ),
                        str(
                            action.get(
                                "description",
                                "",
                            )
                        ),
                        boolean_value(
                            action.get(
                                "enabled"
                            ),
                            True,
                        ),
                        integer_value(
                            action.get(
                                "media_volume"
                            ),
                            100,
                        ),
                        integer_value(
                            action.get(
                                "overlay_screen"
                            ),
                            1,
                        ),
                        integer_value(
                            action.get(
                                "global_cooldown"
                            )
                        ),
                        integer_value(
                            action.get(
                                "user_cooldown"
                            )
                        ),
                        boolean_value(
                            action.get(
                                "fade_enabled"
                            )
                        ),
                        boolean_value(
                            action.get(
                                "repeat_gift_combos"
                            )
                        ),
                        boolean_value(
                            action.get(
                                "skip_on_next_action"
                            )
                        ),
                    )
                )

                for step in action.get(
                    "steps",
                    [],
                ):

                    cursor.execute(
                        """
                        INSERT INTO action_steps
                        (
                            action_id,
                            step_order,
                            step_type,
                            step_value
                        )
                        VALUES
                        (?, ?, ?, ?)
                        """,
                        (
                            action_id,
                            integer_value(
                                step.get(
                                    "order"
                                )
                            ),
                            str(
                                step.get(
                                    "type",
                                    "",
                                )
                            ),
                            str(
                                step.get(
                                    "value",
                                    "",
                                )
                            ),
                        )
                    )

                    action_steps_imported += 1

        if has_event_triggers:

            available_action_ids = {
                row[0]
                for row in cursor.execute(
                    "SELECT id FROM action_presets"
                ).fetchall()
            }

            event_ids = set()

            for event in event_triggers:

                event_id = required_id(
                    event.get(
                        "id"
                    ),
                    "Event trigger",
                )

                if event_id in event_ids:

                    raise ValueError(
                        "The backup contains duplicate event IDs."
                    )

                event_ids.add(
                    event_id
                )

                action_id = required_id(
                    event.get(
                        "action_id"
                    ),
                    "Event trigger action",
                )

                if (
                    action_id
                    not in available_action_ids
                ):

                    raise ValueError(
                        "An event refers to a missing action preset "
                        f"(ID {action_id})."
                    )

                action_mode = str(
                    event.get(
                        "action_mode",
                        "single",
                    )
                    or
                    "single"
                ).lower()

                action_group = event.get(
                    "action_group",
                    "",
                )

                if isinstance(
                    action_group,
                    list,
                ):

                    action_group = json.dumps(
                        action_group
                    )

                else:

                    action_group = str(
                        action_group
                        or
                        ""
                    )

                if (
                    action_mode == "random"
                    and action_group
                ):

                    try:

                        group_ids = [
                            int(value)
                            for value in json.loads(
                                action_group
                            )
                        ]

                    except (
                        TypeError,
                        ValueError,
                        json.JSONDecodeError,
                    ) as error:

                        raise ValueError(
                            "An event contains an invalid random "
                            "action group."
                        ) from error

                    missing_ids = [
                        value
                        for value in group_ids
                        if value
                        not in available_action_ids
                    ]

                    if missing_ids:

                        raise ValueError(
                            "A random event refers to missing action "
                            f"preset IDs: {missing_ids}."
                        )

                    action_group = json.dumps(
                        group_ids
                    )

                cursor.execute(
                    """
                    INSERT INTO event_triggers
                    (
                        id,
                        enabled,
                        trigger_type,
                        trigger_value,
                        user_filter,
                        action_id,
                        action_mode,
                        action_group
                    )
                    VALUES
                    (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        event_id,
                        boolean_value(
                            event.get(
                                "enabled"
                            ),
                            True,
                        ),
                        str(
                            event.get(
                                "trigger_type",
                                "GIFT",
                            )
                        ),
                        str(
                            event.get(
                                "trigger_value",
                                "",
                            )
                        ),
                        str(
                            event.get(
                                "user_filter",
                                "ANY",
                            )
                        ),
                        action_id,
                        action_mode,
                        action_group,
                    )
                )

        if has_legacy_events:

            cursor.execute(
                "DELETE FROM event_actions"
            )

            cursor.execute(
                "DELETE FROM events"
            )

            for event in legacy_events:

                cursor.execute(
                    """
                    INSERT INTO events
                    (
                        enabled,
                        trigger_type,
                        trigger_value,
                        user_filter,
                        action_type,
                        action_value
                    )
                    VALUES
                    (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(
                            event.get(
                                "enabled",
                                True,
                            )
                        ),
                        event.get(
                            "trigger_type",
                            "GIFT",
                        ),
                        event.get(
                            "trigger_value",
                            "",
                        ),
                        event.get(
                            "user_filter",
                            "ANY",
                        ),
                        normalize_action_type(
                            event.get(
                                "action_type"
                            )
                        ),
                        event.get(
                            "action_value"
                        ),
                    )
                )

                event_id = cursor.lastrowid

                actions = event.get(
                    "actions",
                    [],
                )

                if not actions:

                    actions = [
                        {
                            "action_type": event.get(
                                "action_type"
                            ),
                            "action_value": event.get(
                                "action_value"
                            ),
                        }
                    ]

                for action in actions:

                    action_type = normalize_action_type(
                        action.get(
                            "action_type"
                        )
                    )

                    action_value = action.get(
                        "action_value"
                    )

                    if (
                        not action_type
                        or action_value is None
                    ):

                        continue

                    cursor.execute(
                        """
                        INSERT INTO event_actions
                        (
                            event_id,
                            action_type,
                            action_value
                        )
                        VALUES
                        (?, ?, ?)
                        """,
                        (
                            event_id,
                            action_type,
                            action_value,
                        )
                    )

        if has_settings:

            cursor.execute(
                "DELETE FROM settings"
            )

        for setting in settings:

            key = setting.get(
                "key"
            )

            if not key:

                continue

            cursor.execute(
                """
                INSERT INTO settings
                (
                    key,
                    value
                )
                VALUES
                (?, ?)
                ON CONFLICT(key)
                DO UPDATE SET
                    value = excluded.value
                """,
                (
                    key,
                    setting.get(
                        "value",
                        "",
                    ),
                )
            )

        connection.commit()

    normalize_all_action_types()

    return {
        "action_presets_imported": (
            len(action_presets)
            if has_action_presets
            else 0
        ),
        "action_steps_imported": (
            action_steps_imported
        ),
        "event_triggers_imported": (
            len(event_triggers)
            if has_event_triggers
            else 0
        ),
        "events_imported": (
            len(legacy_events)
            if has_legacy_events
            else 0
        ),
        "settings_imported": len(settings),
    }
    
# ==================================================
# Action Steps V2
# ==================================================

def get_action_steps(
    action_id: int,
) -> list[dict]:
    """Get all steps for an action."""

    with closing(get_connection()) as connection:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                id,
                step_order,
                step_type,
                step_value
            FROM action_steps
            WHERE
                action_id = ?
            ORDER BY
                step_order,
                id
            """,
            (
                action_id,
            )
        )

        rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "order": row[1],
                "type": row[2],
                "value": row[3],
            }
            for row in rows
        ]


def add_action_step(
    action_id: int,
    step_order: int,
    step_type: str,
    step_value: str,
) -> None:
    """Add a step to an action."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            INSERT INTO action_steps
            (
                action_id,
                step_order,
                step_type,
                step_value
            )
            VALUES
            (?, ?, ?, ?)
            """,
            (
                action_id,
                step_order,
                step_type,
                step_value,
            )
        )

        connection.commit()


def delete_action_step(
    step_id: int,
) -> None:
    """Delete action step."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            DELETE FROM action_steps
            WHERE
                id = ?
            """,
            (
                step_id,
            )
        )

        connection.commit()
        
# ==================================================
# Event Triggers V2
# ==================================================

def get_event_triggers() -> list[dict]:
    """Get all event triggers."""

    with closing(get_connection()) as connection:

        cursor = connection.cursor()

        cursor.execute(
            """
            SELECT
                event_triggers.id,
                event_triggers.enabled,
                event_triggers.trigger_type,
                event_triggers.trigger_value,
                event_triggers.user_filter,
                event_triggers.action_id,
                event_triggers.action_mode,
                event_triggers.action_group,
                action_presets.name,
                action_presets.duration,
                action_presets.media_volume,
                action_presets.overlay_screen,
                action_presets.global_cooldown,
                action_presets.user_cooldown,
                action_presets.fade_enabled,
                action_presets.repeat_gift_combos,
                action_presets.skip_on_next_action
            FROM event_triggers

            LEFT JOIN action_presets
            ON event_triggers.action_id =
               action_presets.id

            ORDER BY
                event_triggers.id
            """
        )

        rows = cursor.fetchall()

        return [
            {
                "id": row[0],
                "enabled": bool(row[1]),
                "trigger_type": row[2],
                "trigger_value": row[3],
                "user_filter": row[4],
                "action_id": row[5],
                "action_mode": row[6] or "single",
                "action_group": row[7] or "",
                "action": row[8],
                "duration": row[9] or 0,
                "media_volume": row[10] or 100,
                "overlay_screen": row[11] or 1,
                "global_cooldown": row[12] or 0,
                "user_cooldown": row[13] or 0,
                "fade_enabled": bool(row[14]),
                "repeat_gift_combos": bool(row[15]),
                "skip_on_next_action": bool(row[16]),
            }
            for row in rows
        ]


def create_event_trigger(
    trigger_type: str,
    trigger_value: str,
    user_filter: str,
    action_id: int,
    action_mode: str = "single",
    action_group: str = "",
) -> int:
    """Create event trigger."""

    with closing(get_connection()) as connection:

        cursor = connection.execute(
            """
            INSERT INTO event_triggers
            (
                trigger_type,
                trigger_value,
                user_filter,
                action_id,
                action_mode,
                action_group
            )
            VALUES
            (?, ?, ?, ?, ?, ?)
            """,
            (
                trigger_type,
                trigger_value,
                user_filter,
                action_id,
                action_mode,
                action_group,
            )
        )

        connection.commit()

        return cursor.lastrowid


def update_event_trigger(
    trigger_id: int,
    trigger_type: str,
    trigger_value: str,
    user_filter: str,
    action_id: int,
    action_mode: str = "single",
    action_group: str = "",
) -> None:
    """Update event trigger."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            UPDATE event_triggers
            SET
                trigger_type = ?,
                trigger_value = ?,
                user_filter = ?,
                action_id = ?,
                action_mode = ?,
                action_group = ?
            WHERE
                id = ?
            """,
            (
                trigger_type,
                trigger_value,
                user_filter,
                action_id,
                action_mode,
                action_group,
                trigger_id,
            )
        )

        connection.commit()


def update_event_trigger_status(
    trigger_id: int,
    enabled: bool,
) -> None:
    """Update event trigger enabled status."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            UPDATE event_triggers
            SET
                enabled = ?
            WHERE
                id = ?
            """,
            (
                int(enabled),
                trigger_id,
            )
        )

        connection.commit()


def delete_event_trigger(
    trigger_id: int,
) -> None:
    """Delete event trigger."""

    with closing(get_connection()) as connection:

        connection.execute(
            """
            DELETE FROM event_triggers
            WHERE
                id = ?
            """,
            (
                trigger_id,
            )
        )

        connection.commit()
