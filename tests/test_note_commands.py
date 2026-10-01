"""AI-002 dialogue and real callback checks without microphone or motors."""
import ast
from concurrent.futures import ThreadPoolExecutor
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from test_project_notes import notes_module, ProjectNotesStore

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("note_commands_under_test", ROOT / "src/modules/module_note_commands.py")
commands_module = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {"modules.module_project_notes": notes_module}):
    spec.loader.exec_module(commands_module)


class NoteCommandTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.store = ProjectNotesStore(temporary.name)
        self.now = 0
        self.commands = commands_module.NoteCommands(lambda: self.store, clock=lambda: self.now)

    def test_inline_and_spoken_separator(self):
        for i, phrase in enumerate(("Hey TARS, take this note for project X: use the shorter bracket",
                                    "take a note for project X note says use the shorter bracket")):
            self.assertEqual(self.commands.handle(phrase, str(i)), "Saved to project X.")
        self.assertEqual([n.transcript for n in self.store.list_notes("X")], ["use the shorter bracket"] * 2)

    def test_conversational_note_requests_and_noncommands(self):
        for phrase in ("Can you take a note?", "Hey TARS, could you please take a note.",
                       "TARS take note", "Please write a note", "make a note", "save this note"):
            with self.subTest(phrase=phrase):
                self.commands.end_session()
                self.assertTrue(self.commands.claims(phrase))
                self.assertEqual(self.commands.handle(phrase), "Which project is this note for?")
        self.commands.end_session()
        for phrase in ("don't take a note", "how do I take a note", "I told him to take a note"):
            self.assertFalse(self.commands.claims(phrase))
            self.assertIsNone(self.commands.handle(phrase))

    def test_two_turn_literal_commands_and_duplicate_delivery(self):
        self.assertEqual(self.commands.handle("take a note for project X", "start"), "What's the note?")
        content = "  shutdown PC, follow me, take a note for project Y\nKeep this exact.  "
        self.assertEqual(self.commands.handle(content, "body"), "Saved to project X.")
        self.assertTrue(self.commands.claims(content, "body"))
        self.assertEqual(self.commands.handle(content, "body"), "Saved to project X.")
        notes = self.store.list_notes("X")
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].transcript, content)
        self.assertEqual(self.store.list_notes("Y"), [])

    def test_missing_project_retains_inline_content(self):
        self.assertEqual(self.commands.handle("take a note: original words", "a"), "Which project is this note for?")
        self.assertEqual(self.commands.handle("Project Workshop", "b"), "Saved to project Workshop.")
        self.assertEqual(self.store.list_notes("Workshop")[0].transcript, "original words")

    def test_missing_both_and_empty_content(self):
        self.assertIn("Which project", self.commands.handle("take a note"))
        self.assertEqual(self.commands.handle("X"), "What's the note?")
        self.assertIn("didn't hear", self.commands.handle(" "))
        self.assertEqual(self.commands.handle("a thought"), "Saved to project X.")

    def test_cancel_timeout_and_silence_reset(self):
        self.commands.handle("take a note for project X")
        self.assertEqual(self.commands.handle("cancel note"), "Note cancelled.")
        self.commands.handle("take a note for project X")
        self.now = 46
        self.assertIn("timed out", self.commands.handle("shutdown pc"))
        self.commands.handle("take a note for project X")
        self.commands.end_session()
        self.assertIsNone(self.commands.handle("ordinary conversation"))
        self.assertEqual(self.store.list_projects(), [])

    def test_duplicate_prompt_does_not_become_content(self):
        text = "take a note for project X"
        self.assertEqual(self.commands.handle(text, "prompt"), self.commands.handle(text, "prompt"))
        self.assertEqual(self.store.list_projects(), [])

    def test_save_failure_has_no_success_confirmation(self):
        self.commands.store_factory = Mock(side_effect=sqlite3.OperationalError("disk full"))
        self.assertEqual(self.commands.handle("take a note for project X: text"),
                         "I couldn't save that note. Please try again.")
        self.assertIsNone(self.commands.pending)

    def test_movement_guard_at_start_and_save(self):
        self.commands.can_start = lambda: False
        self.assertIn("stop movement", self.commands.handle("take a note for project X"))
        self.commands.can_start = lambda: True
        self.commands.handle("take a note for project X")
        self.commands.can_start = lambda: False
        self.assertIn("haven't saved", self.commands.handle("content"))
        self.assertEqual(self.store.list_projects(), [])

    def test_durable_duplicate_and_conflicting_id(self):
        def save(_):
            return ProjectNotesStore(self.store.data_dir).add_note("X", "text", request_id="event").id
        with ThreadPoolExecutor(max_workers=4) as pool:
            self.assertEqual(len(set(pool.map(save, range(12)))), 1)
        self.assertEqual(len(self.store.list_notes("X")), 1)
        with self.assertRaises(ValueError):
            self.store.add_note("X", "different", request_id="event")

    def test_disabled_and_failed_skill_remain_consumed(self):
        manager = Mock()
        manager.is_enabled.return_value = False
        fake_skills = SimpleNamespace(get_skill_manager=lambda: manager)
        with patch.object(commands_module, "get_voice_note_commands", return_value=self.commands), patch.dict(
                sys.modules, {"modules.module_skills": fake_skills}):
            self.assertIn("disabled", commands_module.route_voice_note("take a note"))
            manager.is_enabled.return_value = True
            manager.execute.return_value = None
            self.assertIn("couldn't process", commands_module.route_voice_note("take a note"))

    def test_stt_emits_ids_and_silence_clears_pending_dictation(self):
        tree = ast.parse((ROOT / "src/modules/module_stt.py").read_text(encoding="utf-8"))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "STTManager")
        methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in
                   ("_emit_result", "_transcribe_utterance")]
        namespace = {"json": json, "uuid4": __import__("uuid").uuid4, "queue_message": Mock(),
                     "set_tars_state": Mock(), "TarsState": SimpleNamespace(STANDBY="standby")}
        exec(compile(ast.Module(body=methods, type_ignores=[]), "module_stt.py", "exec"), namespace)
        fake = SimpleNamespace(_is_meaningful_text=lambda text: True, _last_audio_float32=None,
                               utterance_callback=Mock())
        a = namespace["_emit_result"](fake, "same words")
        b = namespace["_emit_result"](fake, "same words")
        self.assertNotEqual(a["request_id"], b["request_id"])
        self.assertEqual(json.loads(fake.utterance_callback.call_args.args[0]), b)
        self.commands.handle("take a note for project X")
        fake.is_paused = lambda: False
        fake.config = {"STT": {"stt_processor": "fastrtc"}}
        fake.post_utterance_callback = Mock()
        for name in ("_transcribe_with_fastrtc", "_transcribe_silero", "_transcribe_with_server",
                     "_transcribe_with_openai", "_transcribe_with_sherpa_onnx"):
            setattr(fake, name, lambda: None)
        root = ModuleType("modules")
        root.module_speed = Mock()
        with patch.dict(sys.modules, {"modules": root, "modules.module_speed": root.module_speed,
                "modules.module_note_commands": SimpleNamespace(get_voice_note_commands=lambda: self.commands)}):
            namespace["_transcribe_utterance"](fake)
        self.assertIsNone(self.commands.pending)
        fake.post_utterance_callback.assert_not_called()
        namespace["set_tars_state"].assert_called_with("standby")

    def test_real_utterance_callback_routes_notes_before_shutdown_and_llm(self):
        # Execute the actual callback with its imports replaced; importing the
        # whole application would initialize hardware and heavyweight models.
        tree = ast.parse((ROOT / "src/modules/module_main.py").read_text(encoding="utf-8"))
        callback = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "utterance_callback")
        code = compile(ast.Module(body=[callback], type_ignores=[]), "module_main.py", "exec")
        root = ModuleType("modules")
        speed = Mock()
        llm = Mock()
        root.module_speed = speed
        root.module_llm = llm
        async def speak(*args):
            pass
        namespace = dict(json=json, ui_manager=Mock(), stt_manager=SimpleNamespace(), queue_message=Mock(), set_tars_state=Mock(),
                         TarsState=SimpleNamespace(TALKING="talking", LISTENING="listening"),
                         CONFIG={"CHAR": {"character_name": "TARS"}, "TTS": {"ttsoption": "test"}},
                         play_audio_chunks=speak, asyncio=__import__("asyncio"))
        route = SimpleNamespace(route_voice_note=lambda text, request_id: self.commands.handle(text, request_id),
                                get_voice_note_commands=lambda: self.commands)
        with patch.dict(sys.modules, {"modules": root, "modules.module_speed": speed,
                                     "modules.module_llm": llm, "modules.module_note_commands": route}):
            exec(code, namespace)
            namespace["utterance_callback"](json.dumps({"text": "take a note for project X: shutdown pc", "request_id": "event"}))
        namespace["queue_message"].assert_any_call("VOICE ROUTE: project_notes")
        namespace["queue_message"].assert_any_call("NOTES: Saved to project X.")
        self.assertEqual(self.store.list_notes("X")[0].transcript, "shutdown pc")
        self.assertEqual(llm.mock_calls, [])
        self.assertTrue(namespace['stt_manager']._note_session_complete)

    def test_completed_note_does_not_open_another_listening_round(self):
        tree = ast.parse((ROOT / 'src/modules/module_main.py').read_text(encoding='utf-8'))
        callback = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'post_utterance_callback')
        stt = SimpleNamespace(_note_session_complete=True, _transcribe_utterance=Mock())
        namespace = dict(stt_manager=stt, set_tars_state=Mock(), queue_message=Mock(),
                         TarsState=SimpleNamespace(STANDBY='standby'))
        exec(compile(ast.Module(body=[callback], type_ignores=[]), 'module_main.py', 'exec'), namespace)
        namespace['post_utterance_callback']()
        stt._transcribe_utterance.assert_not_called()
        self.assertFalse(stt._note_session_complete)
        namespace['set_tars_state'].assert_called_once_with('standby')

    def test_real_capture_loop_bounds_stalled_audio_and_continuous_noise(self):
        tree = ast.parse((ROOT / 'src/modules/module_stt.py').read_text(encoding='utf-8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'STTManager')
        methods = [n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name in
                   ('_record_audio_chunks', '_listening_expired')]
        for speech, step, maximum_reads in ((False, 5.0, 2), (True, .25, 100)):
            with self.subTest(speech=speech):
                clock = [0.0]
                def read(_):
                    clock[0] += step
                    return b'frame', False
                mic = Mock()
                mic.__enter__ = Mock(return_value=mic)
                mic.__exit__ = Mock(return_value=False)
                mic.read = Mock(side_effect=read)
                namespace = dict(time=SimpleNamespace(monotonic=lambda: clock[0]),
                                 ResamplingInputStream=lambda **kw: mic, is_tts_playing=lambda: False,
                                 queue_message=Mock(), set_tars_state=Mock())
                exec(compile(ast.Module(body=methods, type_ignores=[]), 'module_stt.py', 'exec'), namespace)
                vad = lambda data, detected, silent: (False, speech, 0)
                fake = SimpleNamespace(MAX_SILENT_FRAMES=15, MAX_RECORDING_FRAMES=1000,
                    vadmethod='rms', smart_turn_session=None, smart_turn_audio_buffer=[],
                    _is_silence_detected_rms=vad, _is_silence_detected_silero=vad,
                    _is_silence_detected_sherpa_onnx=vad, is_paused=lambda: False,
                    shutdown_event=SimpleNamespace(is_set=lambda: False),
                    _get_progress_bar=lambda: (Mock(), Mock()))
                fake._listening_expired = lambda start, detected: namespace['_listening_expired'](fake, start, detected)
                with patch.dict(sys.modules, {'modules.module_tts': SimpleNamespace(needs_mic_flush=lambda: False, clear_mic_flush=lambda: None)}):
                    self.assertEqual(namespace['_record_audio_chunks'](fake), (None, 0))
                self.assertLessEqual(mic.read.call_count, maximum_reads)


if __name__ == "__main__":
    unittest.main()
