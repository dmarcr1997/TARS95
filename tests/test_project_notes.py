"""Hardware-free acceptance checks for AI-001. Uses disposable storage only."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "src/modules/module_project_notes.py"
spec = importlib.util.spec_from_file_location("project_notes_under_test", MODULE_PATH)
notes_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = notes_module
spec.loader.exec_module(notes_module)
ProjectNotesStore = notes_module.ProjectNotesStore


class ProjectNotesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = ProjectNotesStore(self.root / "notes")

    def test_process_restart_preserves_original_transcript_and_identity(self):
        transcript = "  Use the shorter bracket.\nCafé — don't follow me.  "
        note = self.store.add_note("Project X", transcript)
        code = (
            "import sys; from modules.module_project_notes import ProjectNotesStore; "
            "n=ProjectNotesStore(sys.argv[1]).get_note(sys.argv[2]); "
            "assert n.transcript == sys.argv[3]; assert n.project == 'Project X'; "
            "print(n.id)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code, str(self.store.data_dir), note.id, transcript],
            cwd=MODULE_PATH.parents[1], capture_output=True, text=True, check=True,
        )
        self.assertEqual(result.stdout.strip(), note.id)
        self.assertEqual(datetime.fromisoformat(note.created_at).utcoffset().total_seconds(), 0)

    def test_project_matching_and_isolation(self):
        first = self.store.add_note("  Project   X ", "one")
        second = self.store.add_note("project x", "two")
        self.store.add_note("Project Y", "other")
        self.assertEqual(first.project_id, second.project_id)
        self.assertEqual([n.transcript for n in self.store.list_notes("PROJECT X")], ["one", "two"])
        self.assertEqual(len(self.store.list_projects()), 2)
        self.assertIsNone(self.store.get_note("missing"))
        self.assertEqual(self.store.list_notes("missing"), [])
        with self.assertRaises(KeyError):
            self.store.export_project("missing")

    def test_export_uses_opaque_paths_and_preserves_literal_content(self):
        for name in ("../../outside", r"C:\outside", "'; DROP TABLE notes; --"):
            with self.subTest(project=name):
                transcript = "```\n<script>example</script>\n````\n# literal heading"
                note = self.store.add_note(name, transcript)
                path = self.store.export_project(name)
                self.assertEqual(path.parent, self.store.data_dir)
                self.assertEqual(path.name, f"project-{note.project_id}.md")
                content = path.read_text(encoding="utf-8")
                self.assertIn(transcript, content)
                self.assertIn("`````text\n", content)
                self.assertIn(note.id, content)
                self.assertIn(note.created_at, content)
                self.store.add_note(name, "second note")
                self.assertEqual(self.store.export_project(name), path)
                self.assertIn("second note", path.read_text(encoding="utf-8"))

    def test_concurrent_writers_do_not_lose_notes_or_duplicate_projects(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            saved = list(pool.map(lambda i: self.store.add_note("shared", f"note {i}"), range(40)))
        self.assertEqual(len({n.id for n in saved}), 40)
        self.assertEqual(len(self.store.list_projects()), 1)
        self.assertEqual({n.transcript for n in self.store.list_notes("shared")},
                         {f"note {i}" for i in range(40)})

    def test_invalid_input_does_not_create_projects(self):
        for project, transcript in (("", "note"), ("x" * 201, "note"), (None, "note"),
                                    ("x\x00", "note"), ("x", "  "), ("x", None)):
            with self.subTest(project=project, transcript=transcript):
                with self.assertRaises(ValueError):
                    self.store.add_note(project, transcript)
        self.assertEqual(self.store.list_projects(), [])

    def test_failed_insert_rolls_back_new_project_and_raises(self):
        with closing(sqlite3.connect(self.store.db_path)) as db:
            db.execute("CREATE TRIGGER fail_note BEFORE INSERT ON notes "
                       "BEGIN SELECT RAISE(ABORT, 'simulated write failure'); END")
            db.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.add_note("unsaved", "never claim success")
        self.assertEqual(self.store.list_projects(), [])

    def test_failed_export_keeps_previous_snapshot_and_cleans_temp_file(self):
        self.store.add_note("x", "saved")
        path = self.store.export_project("x")
        original = path.read_bytes()
        self.store.add_note("x", "new")
        with patch.object(notes_module.os, "replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.store.export_project("x")
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(list(self.store.data_dir.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
