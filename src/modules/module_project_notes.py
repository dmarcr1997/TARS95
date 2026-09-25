"""Durable, local project notes; standard library only, with no robot imports.

ProjectNotesStore() uses src/data/project_notes/notes.sqlite3 regardless of cwd.
Pass a data_dir to use another location (including an isolated test directory).
Public writes return only after commit; SQLite and filesystem errors propagate
to the caller, which must not announce success when an operation fails.

Usage from the src import path::

    store = ProjectNotesStore()
    note = store.add_note("Project X", "Use the shorter bracket.")
    restored = store.get_note(note.id)
    history = store.list_notes("project x")
    markdown_path = store.export_project("Project X")

The database is the source of truth; Markdown files are replaceable snapshots.
Back up notes.sqlite3 while no writes are running, or use SQLite's backup API
for a live backup. No microphone, LLM, motion, or voice confirmation is invoked.
"""

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import tempfile
import unicodedata
from uuid import uuid4


DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "project_notes"


@dataclass(frozen=True)
class Project:
    id: str
    name: str


@dataclass(frozen=True)
class Note:
    id: str
    project_id: str
    project: str
    transcript: str
    created_at: str


def _project_name(value):
    if not isinstance(value, str):
        raise ValueError("Project name must be text")
    name = " ".join(unicodedata.normalize("NFC", value).split())
    if not name or len(name) > 200 or any(unicodedata.category(c).startswith("C") for c in name):
        raise ValueError("Project name must contain 1–200 printable characters")
    return name, name.casefold()


class ProjectNotesStore:
    """Independent connections per operation support voice/UI worker threads.

    Names match case-insensitively with normalized whitespace; the first saved
    spelling is retained. Project names are database values, never filesystem
    paths. Transcripts are preserved exactly, including whitespace and newlines.
    """

    def __init__(self, data_dir=None):
        self.data_dir = Path(data_dir if data_dir is not None else DEFAULT_DATA_DIR).resolve()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "notes.sqlite3"
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    name_key TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS notes (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    id TEXT NOT NULL UNIQUE,
                    project_id TEXT NOT NULL REFERENCES projects(id),
                    transcript TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS notes_by_project
                    ON notes(project_id, sequence);
            """)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.db_path, timeout=10)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("PRAGMA synchronous = FULL")
            with db:
                yield db
        finally:
            db.close()

    def add_note(self, project, transcript):
        """Atomically create/find a project and save one note. Return a Note."""
        name, key = _project_name(project)
        if not isinstance(transcript, str) or not transcript.strip():
            raise ValueError("Note transcript must contain text")
        with self._connect() as db:
            db.execute(
                "INSERT INTO projects(id, name, name_key) VALUES (?, ?, ?) "
                "ON CONFLICT(name_key) DO NOTHING", (uuid4().hex, name, key),
            )
            row = db.execute("SELECT id, name FROM projects WHERE name_key = ?", (key,)).fetchone()
            note = Note(uuid4().hex, row["id"], row["name"], transcript,
                        datetime.now(timezone.utc).isoformat(timespec="microseconds"))
            db.execute(
                "INSERT INTO notes(id, project_id, transcript, created_at) VALUES (?, ?, ?, ?)",
                (note.id, note.project_id, note.transcript, note.created_at),
            )
        return note

    def list_projects(self):
        with self._connect() as db:
            return [Project(**dict(row)) for row in db.execute(
                "SELECT id, name FROM projects ORDER BY name_key")]

    @staticmethod
    def _note(row):
        return Note(**dict(row)) if row is not None else None

    def get_note(self, note_id):
        """Return a Note, or None for an unknown ID."""
        with self._connect() as db:
            return self._note(db.execute(
                "SELECT n.id, n.project_id, p.name AS project, n.transcript, n.created_at "
                "FROM notes n JOIN projects p ON p.id = n.project_id WHERE n.id = ?",
                (note_id,),
            ).fetchone())

    def list_notes(self, project):
        """Return notes in insertion order; an unknown project returns []."""
        _, key = _project_name(project)
        with self._connect() as db:
            return [self._note(row) for row in db.execute(
                "SELECT n.id, n.project_id, p.name AS project, n.transcript, n.created_at "
                "FROM notes n JOIN projects p ON p.id = n.project_id "
                "WHERE p.name_key = ? ORDER BY n.sequence", (key,),
            )]

    def export_project(self, project):
        """Write a consistent Markdown snapshot and return its absolute Path.

        Exports live beside the database as project-<opaque ID>.md. A temporary
        file and atomic replace prevent partial exports and replace an existing
        filename symlink rather than following it. Unknown projects raise
        KeyError. Re-export refreshes the same project's snapshot.
        """
        notes = self.list_notes(project)
        if not notes:
            raise KeyError(f"Unknown project: {project}")
        first = notes[0]
        # Escape the heading; literal fenced transcripts preserve dictated text
        # without treating embedded HTML or Markdown as formatting/instructions.
        heading = "".join("\\" + c if c in r"\`*_{}[]<>()#+-.!|" else c for c in first.project)
        chunks = [f"# Project: {heading}\n\n"]
        for note in notes:
            fence = "```"
            while fence in note.transcript:
                fence += "`"
            chunks.append(f"## {note.created_at}\n\nNote ID: {note.id}\n\n"
                          f"{fence}text\n{note.transcript}\n{fence}\n\n")
        destination = self.data_dir / f"project-{first.project_id}.md"
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                             dir=self.data_dir, suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write("".join(chunks))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, destination)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return destination
