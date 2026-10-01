"""Deterministic voice-note dialogue. No hardware, LLM, or filesystem at import.

Inline syntax: 'take a note for project X: text' (also ', note says text').
Without a separator, ask for the content rather than guess project boundaries.
Pending dictation expires after 45 seconds; its next late utterance is consumed
with a timeout response, never routed as a robot command. Explicit cancel is
reserved during dictation. All other note content is literal data.
"""
from collections import OrderedDict
import re
import sqlite3
import threading
import time

from modules.module_project_notes import ProjectNotesStore, _project_name


START = re.compile(
    r"^(?:(?:hey\s+)?tars?[,!:.]?\s+)?"
    r"(?:please\s+)?(?:(?:can|could|would|will)\s+you\s+)?(?:please\s+)?"
    r"(?:take|make|write|save)\s+(?:(?:a|this)\s+)?note\b", re.I,
)
CANCEL = re.compile(r"^(?:hey\s+tars?[,!:.]?\s+)?(?:cancel(?:\s+(?:the\s+)?note)?|never\s*mind)[.!?]*$", re.I)


class NoteCommands:
    def __init__(self, store_factory=ProjectNotesStore, clock=time.monotonic, timeout=45, can_start=lambda: True):
        self.store_factory = store_factory
        self.clock = clock
        self.timeout = timeout
        self.can_start = can_start
        self.pending = None
        self.replies = OrderedDict()
        self.lock = threading.RLock()

    def claims(self, text, request_id=None):
        with self.lock:
            return request_id in self.replies or self.pending is not None or START.match(text.strip()) is not None

    def end_session(self):
        with self.lock:
            self.pending = None

    def awaiting_input(self):
        with self.lock:
            return self.pending is not None

    def handle(self, text, request_id=None):
        with self.lock:
            if request_id and request_id in self.replies:
                original, reply = self.replies[request_id]
                return reply if original == text else "That request ID was already used. Please repeat the note."
            reply = self._handle(text, request_id)
            if reply is not None and request_id:
                self.replies[request_id] = (text, reply)
                while len(self.replies) > 128:
                    self.replies.popitem(last=False)
            return reply

    def _handle(self, text, request_id):
        clean = text.strip()
        if self.pending:
            if CANCEL.fullmatch(clean):
                self.pending = None
                return "Note cancelled."
            if self.clock() >= self.pending["deadline"]:
                self.pending = None
                return "Note timed out. Please say take a note again."
            if not clean:
                return "I didn't hear anything. Please repeat, or say cancel note."
            if self.pending["project"] is None:
                project = re.sub(r"^(?:for\s+)?project\s+", "", clean, flags=re.I).rstrip(".!?")
                return self._prepare(project, self.pending["content"], request_id)
            return self._save(self.pending["project"], text, request_id)
        match = START.match(clean)
        if not match:
            return None
        if not self.can_start():
            return "Please stop movement before taking a note."
        rest = clean[match.end():].strip()
        # Colon is unambiguous; spoken 'note says' works with punctuation-free STT.
        parts = re.split(r"\s*:\s*|\s*[,.;]?\s+note\s+says\s+", rest, maxsplit=1, flags=re.I)
        project_part = parts[0].strip().rstrip(".!?")
        content = parts[1] if len(parts) == 2 and parts[1].strip() else None
        project_match = re.fullmatch(r"(?:for|on)\s+project(?:\s+(.+))?", project_part, re.I)
        project = project_match.group(1) if project_match else None
        if project_part and not project_match:
            return "Please say take a note for project, then the project name. Use note says before inline content."
        return self._prepare(project, content, request_id)

    def _prepare(self, project, content, request_id):
        if project is not None:
            try:
                project, _ = _project_name(project)
            except ValueError:
                self.pending = None
                return "That project name isn't valid. Please start the note again."
        if project and content is not None:
            return self._save(project, content, request_id)
        self.pending = {"project": project, "content": content, "deadline": self.clock() + self.timeout}
        return "What's the note?" if project else "Which project is this note for?"

    def _save(self, project, content, request_id):
        self.pending = None
        if not self.can_start():
            return "Movement started. I haven't saved the note. Stop movement and try again."
        try:
            note = self.store_factory().add_note(project, content, request_id=request_id)
        except (OSError, ValueError, sqlite3.Error):
            return "I couldn't save that note. Please try again."
        return f"Saved to project {note.project}."


_voice_commands = None
_instance_lock = threading.Lock()


def get_voice_note_commands():
    global _voice_commands
    with _instance_lock:
        if _voice_commands is None:
            def stationary():
                from modules import module_servoctl
                return not module_servoctl.MOVING
            _voice_commands = NoteCommands(can_start=stationary)
        return _voice_commands


def route_voice_note(text, request_id=None):
    """Return a reply or None; disabled commands remain consumed, never LLM-routed."""
    commands = get_voice_note_commands()
    if not commands.claims(text, request_id):
        return None
    from modules.module_skills import get_skill_manager
    skills = get_skill_manager()
    if skills is None or not skills.is_enabled("project_notes"):
        commands.end_session()
        return "Project notes are disabled. Enable the project notes skill first."
    reply = skills.execute("project_notes", {}, {
        "source": "voice", "user_input": text, "request_id": request_id,
    })
    return reply if reply is not None else "I couldn't process that note. Please try again."
