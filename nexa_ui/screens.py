"""
NEXA UI - Screens

Home, Participants, Session (assessment control panel), History, and
System Check. Each screen is a QWidget swapped into the main window's stack.
"""

import json
import os
import shutil
import subprocess

from PyQt5.QtCore import Qt, QUrl, pyqtSignal, QTimer
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QFrame, QLineEdit, QSpinBox, QComboBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QAbstractItemView, QTextEdit, QScrollArea,
    QDialog, QDialogButtonBox, QFormLayout, QFileDialog, QInputDialog,
)

import config
import modalities
import report
import theme
from runner import AssessmentRunner


def card(title=None):
    frame = QFrame()
    frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(18, 18, 18, 18)
    if title:
        lbl = QLabel(title)
        lbl.setObjectName("H2")
        layout.addWidget(lbl)
    return frame, layout


def show_metrics_dialog(parent, title, metrics):
    """Display all stored metrics for a completed modality run."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(f"{title} analysis details")
    dialog.resize(min(760, config.SCREEN_WIDTH - 40),
                  min(520, config.SCREEN_HEIGHT - 40))
    layout = QVBoxLayout(dialog)

    heading = QLabel("Analysis details")
    heading.setObjectName("H2")
    layout.addWidget(heading)

    table = QTableWidget(len(metrics), 2, dialog)
    table.setHorizontalHeaderLabels(["Measurement", "Value"])
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
    for row, (key, value) in enumerate(sorted(metrics.items())):
        label = key.replace("_", " ").strip().title()
        if isinstance(value, (dict, list, tuple)):
            display = json.dumps(value, indent=2, sort_keys=True)
        elif value is None:
            display = "Not available"
        else:
            display = str(value)
        table.setItem(row, 0, QTableWidgetItem(label))
        table.setItem(row, 1, QTableWidgetItem(display))
    table.resizeRowsToContents()
    layout.addWidget(table, 1)

    buttons = QDialogButtonBox(QDialogButtonBox.Close)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    dialog.exec_()


def _speech_task_key(run, metrics):
    task = metrics.get("task")
    if not task and run["raw_path"]:
        summary_path = os.path.join(run["raw_path"], "speech_summary.json")
        try:
            with open(summary_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
            if isinstance(payload, dict):
                task = payload.get("task")
        except (OSError, json.JSONDecodeError):
            pass
    return str(task or "")


def show_baseline_comparison_dialog(parent, baseline_run, current_run, db, task):
    modality = modalities.get(current_run["modality"])
    baseline_metrics = db.run_metrics(baseline_run)
    current_metrics = db.run_metrics(current_run)
    dialog = QDialog(parent)
    dialog.setWindowTitle(f"{modality.name} baseline comparison")
    dialog.resize(min(820, config.SCREEN_WIDTH - 30),
                  min(520, config.SCREEN_HEIGHT - 30))
    layout = QVBoxLayout(dialog)

    heading = QLabel(modality.name + (f" - {task.replace('_', ' ').title()}" if task else ""))
    heading.setObjectName("H1")
    layout.addWidget(heading)
    context = QLabel(
        f"Baseline: {baseline_run['started_at']}   Current: {current_run['started_at']}"
    )
    context.setObjectName("Dim")
    layout.addWidget(context)

    table = QTableWidget(len(modality.metrics), 5, dialog)
    table.setHorizontalHeaderLabels(
        ["Measurement", "Baseline", "Current", "Change", "Change %"]
    )
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    for row, metric in enumerate(modality.metrics):
        baseline = baseline_metrics.get(metric.key)
        current = current_metrics.get(metric.key)
        change = None
        percent = None
        if isinstance(baseline, (int, float)) and isinstance(current, (int, float)):
            change = current - baseline
            if baseline != 0:
                percent = 100.0 * change / baseline
        values = [
            metric.label,
            metric.format(baseline),
            metric.format(current),
            "Not available" if change is None else f"{change:+.{metric.precision}f}",
            "Not available" if percent is None else f"{percent:+.1f}%",
        ]
        for column, value in enumerate(values):
            table.setItem(row, column, QTableWidgetItem(value))
    layout.addWidget(table, 1)

    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dialog.accept)
    layout.addWidget(close_btn)
    dialog.exec_()


def show_session_results_dialog(parent, db, session_id):
    """Display every saved assessment run for one session."""
    runs = list(db.list_runs(session_id))
    dialog = QDialog(parent)
    dialog.setWindowTitle(f"Session {session_id} assessment results")
    dialog.resize(min(900, config.SCREEN_WIDTH - 30),
                  min(540, config.SCREEN_HEIGHT - 30))
    layout = QVBoxLayout(dialog)

    heading = QLabel("Assessment results")
    heading.setObjectName("H1")
    layout.addWidget(heading)

    session = db.get_session(session_id)
    participant_id = session["participant_id"]
    table = QTableWidget(len(runs), 6, dialog)
    table.setHorizontalHeaderLabels(
        ["Assessment", "Task", "Started", "Status", "Quality", "Baseline"]
    )
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.SingleSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    for row, run in enumerate(runs):
        modality = modalities.get(run["modality"])
        metrics = db.run_metrics(run)
        task_key = _speech_task_key(run, metrics) if run["modality"] == "speech" else ""
        task = task_key.replace("_", " ").title()
        quality = str(metrics.get("quality_status") or "")
        baseline = db.get_baseline_run(participant_id, run["modality"], task_key)
        values = [
            modality.name if modality else run["modality"].replace("_", " ").title(),
            task or "Not specified",
            run["started_at"],
            run["status"].title(),
            quality or "Not reported",
            "Yes" if baseline is not None and baseline["id"] == run["id"] else "",
        ]
        for column, value in enumerate(values):
            table.setItem(row, column, QTableWidgetItem(value))

    table.resizeRowsToContents()
    layout.addWidget(table, 1)

    if not runs:
        empty = QLabel("No assessment results have been saved for this session.")
        empty.setObjectName("Dim")
        layout.addWidget(empty)

    button_row = QHBoxLayout()
    details_btn = QPushButton("Show details")
    details_btn.setEnabled(bool(runs))
    baseline_btn = QPushButton("Set as baseline")
    compare_btn = QPushButton("Compare to baseline")
    baseline_btn.setEnabled(False)
    compare_btn.setEnabled(False)
    close_btn = QPushButton("Close")
    close_btn.clicked.connect(dialog.accept)
    button_row.addWidget(details_btn)
    button_row.addWidget(baseline_btn)
    button_row.addWidget(compare_btn)
    button_row.addStretch()
    button_row.addWidget(close_btn)
    layout.addLayout(button_row)

    def show_selected_run():
        row = table.currentRow()
        if row < 0 or row >= len(runs):
            QMessageBox.information(dialog, "No selection",
                                    "Select an assessment first.")
            return
        run = runs[row]
        modality = modalities.get(run["modality"])
        metrics = db.run_metrics(run)
        task_key = (_speech_task_key(run, metrics)
                    if run["modality"] == "speech" else "")
        task = task_key.replace("_", " ").title()
        name = modality.name if modality else run["modality"].title()
        if task:
            name = f"{name} - {task}"
        show_metrics_dialog(dialog, name, metrics)

    details_btn.clicked.connect(show_selected_run)
    table.doubleClicked.connect(lambda _index: show_selected_run())

    def selected_assessment_run():
        row = table.currentRow()
        if row < 0 or row >= len(runs):
            return None, ""
        run = runs[row]
        if modalities.get(run["modality"]) is None or run["status"] != "completed":
            return None, ""
        task = (_speech_task_key(run, db.run_metrics(run))
                if run["modality"] == "speech" else "")
        if run["modality"] == "speech" and not task:
            return None, ""
        return run, task

    def update_baseline_actions():
        run, task = selected_assessment_run()
        valid = run is not None
        baseline_btn.setEnabled(valid)
        baseline = (db.get_baseline_run(participant_id, run["modality"], task)
                    if valid else None)
        compare_btn.setEnabled(valid and baseline is not None)

    def set_baseline():
        run, task = selected_assessment_run()
        if run is None:
            return
        reply = QMessageBox.question(
            dialog, "Set assessment baseline",
            f"Use this {modalities.get(run['modality']).name} "
            f"{task.replace('_', ' ')} assessment as the participant baseline?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            db.set_baseline_run(participant_id, run["modality"], task, run["id"])
        except Exception as exc:
            QMessageBox.critical(dialog, "Baseline error", str(exc))
            return
        for row_index, candidate in enumerate(runs):
            if candidate["modality"] != run["modality"]:
                continue
            candidate_task = (_speech_task_key(candidate, db.run_metrics(candidate))
                              if candidate["modality"] == "speech" else "")
            if candidate_task == task:
                table.item(row_index, 5).setText(
                    "Yes" if candidate["id"] == run["id"] else ""
                )
        update_baseline_actions()

    def compare_baseline():
        run, task = selected_assessment_run()
        if run is None:
            return
        baseline = db.get_baseline_run(participant_id, run["modality"], task)
        if baseline is None:
            QMessageBox.information(dialog, "No baseline",
                                    "Set a baseline for this assessment first.")
            return
        show_baseline_comparison_dialog(dialog, baseline, run, db, task)

    baseline_btn.clicked.connect(set_baseline)
    compare_btn.clicked.connect(compare_baseline)
    table.itemSelectionChanged.connect(update_baseline_actions)
    if runs:
        table.selectRow(0)
        update_baseline_actions()
    dialog.exec_()


# ===========================================================================
# HOME
# ===========================================================================

class HomeScreen(QWidget):
    navigate = pyqtSignal(str)

    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        title = QLabel("NEXA")
        title.setObjectName("H1")
        subtitle = QLabel("Neuromuscular Evaluation and eXamination Assistant")
        subtitle.setObjectName("Dim")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        actions = QHBoxLayout()
        new_btn = QPushButton("Start new session")
        new_btn.setObjectName("Primary")
        new_btn.setMinimumHeight(70)
        new_btn.clicked.connect(lambda: self.navigate.emit("participants"))

        hist_btn = QPushButton("Session history")
        hist_btn.setMinimumHeight(70)
        hist_btn.clicked.connect(lambda: self.navigate.emit("history"))

        sys_btn = QPushButton("System check")
        sys_btn.setMinimumHeight(70)
        sys_btn.clicked.connect(lambda: self.navigate.emit("system"))

        actions.addWidget(new_btn, 2)
        actions.addWidget(hist_btn, 1)
        actions.addWidget(sys_btn, 1)
        layout.addLayout(actions)

        stats_frame, stats_layout = card("At a glance")
        self.stats_label = QLabel()
        self.stats_label.setObjectName("Dim")
        stats_layout.addWidget(self.stats_label)
        layout.addWidget(stats_frame)

        layout.addStretch()

        notice = QLabel(config.RESEARCH_NOTICE)
        notice.setObjectName("Notice")
        notice.setWordWrap(True)
        layout.addWidget(notice)

    def refresh(self):
        participants = self.db.list_participants()
        sessions = self.db.list_sessions()
        self.stats_label.setText(
            f"{len(participants)} participant record(s) · {len(sessions)} session(s) recorded"
        )


# ===========================================================================
# PARTICIPANTS
# ===========================================================================

class NewParticipantDialog(QDialog):
    def __init__(self, db, parent=None):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("New participant")
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("e.g. NEXA-014 (de-identified code)")
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Optional label")
        self.year_spin = QSpinBox()
        self.year_spin.setRange(0, 2100)
        self.year_spin.setSpecialValueText("—")
        self.year_spin.setValue(0)
        self.hand_combo = QComboBox()
        self.hand_combo.addItems(["", "Right", "Left", "Ambidextrous"])
        self.notes_edit = QLineEdit()

        form.addRow("Participant code *", self.code_edit)
        form.addRow("Name / label", self.name_edit)
        form.addRow("Birth year", self.year_spin)
        form.addRow("Handedness", self.hand_combo)
        form.addRow("Notes", self.notes_edit)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.participant_id = None

    def _accept(self):
        code = self.code_edit.text().strip()
        if not code:
            QMessageBox.warning(self, "Missing code", "A participant code is required.")
            return
        if self.db.participant_code_exists(code):
            QMessageBox.warning(self, "Duplicate code",
                                f"Participant code '{code}' already exists.")
            return
        try:
            self.participant_id = self.db.create_participant(
                code=code,
                display_name=self.name_edit.text(),
                birth_year=self.year_spin.value() or None,
                handedness=self.hand_combo.currentText(),
                notes=self.notes_edit.text(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Database error", str(e))
            return
        self.accept()


class ParticipantsScreen(QWidget):
    session_started = pyqtSignal(int)   # session_id

    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Participants")
        title.setObjectName("H1")
        header.addWidget(title)
        header.addStretch()
        new_btn = QPushButton("+ New participant")
        new_btn.setObjectName("Primary")
        new_btn.clicked.connect(self._new_participant)
        header.addWidget(new_btn)
        layout.addLayout(header)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by code or name…")
        self.search.textChanged.connect(self.refresh)
        layout.addWidget(self.search)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Code", "Name / label", "Birth year", "Sessions"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        self.operator_edit = QLineEdit()
        self.operator_edit.setPlaceholderText("Operator name (recorded with the session)")
        layout.addWidget(self.operator_edit)

        start_btn = QPushButton("Start session with selected participant")
        start_btn.setObjectName("Primary")
        start_btn.setMinimumHeight(56)
        start_btn.clicked.connect(self._start_session)
        layout.addWidget(start_btn)

    def refresh(self):
        rows = self.db.list_participants(self.search.text().strip())
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            n_sessions = len(self.db.list_sessions(row["id"]))
            values = [
                row["code"],
                row["display_name"] or "—",
                str(row["birth_year"]) if row["birth_year"] else "—",
                str(n_sessions),
            ]
            for j, v in enumerate(values):
                item = QTableWidgetItem(v)
                if j == 0:
                    item.setData(Qt.UserRole, row["id"])
                self.table.setItem(i, j, item)

    def _selected_participant_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _new_participant(self):
        dlg = NewParticipantDialog(self.db, self)
        if dlg.exec_() == QDialog.Accepted:
            self.refresh()

    def _start_session(self):
        pid = self._selected_participant_id()
        if pid is None:
            QMessageBox.information(self, "No selection",
                                    "Select a participant first, or create a new one.")
            return
        try:
            session_id = self.db.start_session(
                pid, operator=self.operator_edit.text().strip()
            )
        except Exception as e:
            QMessageBox.critical(self, "Database error", str(e))
            return
        self.session_started.emit(session_id)


# ===========================================================================
# SESSION (assessment control panel)
# ===========================================================================

class ModalityTile(QFrame):
    run_requested = pyqtSignal(str)
    details_requested = pyqtSignal(str)

    def __init__(self, modality):
        super().__init__()
        self.modality = modality
        self.setObjectName("Card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(6)

        name = QLabel(modality.name)
        name.setObjectName("H2")
        layout.addWidget(name)

        sub = QLabel(modality.subtitle)
        sub.setObjectName("Dim")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        self.status_label = QLabel("Not yet run")
        self.status_label.setObjectName("Dim")
        layout.addWidget(self.status_label)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        layout.addStretch()

        button_row = QHBoxLayout()
        self.details_btn = QPushButton("Show details")
        self.details_btn.setMinimumHeight(config.TOUCH_MIN_BUTTON_HEIGHT)
        self.details_btn.setVisible(False)
        self.details_btn.clicked.connect(
            lambda: self.details_requested.emit(modality.key))
        button_row.addWidget(self.details_btn)

        self.run_btn = QPushButton("Run assessment")
        self.run_btn.setObjectName("Primary")
        self.run_btn.setMinimumHeight(config.TOUCH_MIN_BUTTON_HEIGHT)
        self.run_btn.clicked.connect(lambda: self.run_requested.emit(modality.key))
        button_row.addWidget(self.run_btn, 1)
        layout.addLayout(button_row)

        if not modality.is_available():
            self.run_btn.setEnabled(False)
            self.status_label.setText("Program not configured")
            self.status_label.setStyleSheet(f"color: {theme.ERROR};")

    def update_from_run(self, run_row, metrics_pairs):
        if run_row is None:
            return
        status = run_row["status"]
        colour = {"completed": theme.OK, "aborted": theme.WARN,
                  "failed": theme.ERROR}.get(status, theme.TEXT_DIM)
        self.status_label.setText(f"Last run: {status} — {run_row['started_at']}")
        self.status_label.setStyleSheet(f"color: {colour};")
        text = "   ".join(f"{label}: {value}" for label, value in metrics_pairs
                          if value != "—")
        self.summary_label.setText(text or "No metrics read")
        self.details_btn.setVisible(True)
        self.run_btn.setText("Run again")


class SessionScreen(QWidget):
    session_ended = pyqtSignal()

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.session_id = None
        self.tiles = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        head_box = QVBoxLayout()
        self.title = QLabel("Session")
        self.title.setObjectName("H1")
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("Dim")
        head_box.addWidget(self.title)
        head_box.addWidget(self.subtitle)
        header.addLayout(head_box)
        header.addStretch()

        report_btn = QPushButton("Generate report")
        report_btn.clicked.connect(self._generate_report)
        header.addWidget(report_btn)

        results_btn = QPushButton("Assessment results")
        results_btn.clicked.connect(self._show_all_results)
        header.addWidget(results_btn)

        end_btn = QPushButton("End session")
        end_btn.setObjectName("Danger")
        end_btn.clicked.connect(self._end_session)
        header.addWidget(end_btn)
        layout.addLayout(header)

        grid_host = QWidget()
        self.grid = QGridLayout(grid_host)
        self.grid.setSpacing(12)
        for i, modality in enumerate(modalities.REGISTRY):
            tile = ModalityTile(modality)
            tile.run_requested.connect(self._run_modality)
            tile.details_requested.connect(self._show_modality_details)
            self.tiles[modality.key] = tile
            self.grid.addWidget(tile, i // 2, i % 2)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(grid_host)
        scroll.setFrameShape(QFrame.NoFrame)
        layout.addWidget(scroll, 1)

        notes_frame, notes_layout = card("Session notes")
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(70)
        self.notes_edit.setPlaceholderText(
            "Conditions, deviations from protocol, anything affecting interpretation of the raw data…"
        )
        notes_layout.addWidget(self.notes_edit)
        layout.addWidget(notes_frame)

    def load_session(self, session_id):
        self.session_id = session_id
        session = self.db.get_session(session_id)
        participant = self.db.get_participant(session["participant_id"])
        self.title.setText(f"Session {session_id} — {participant['code']}")
        operator = session["operator"] or "unspecified operator"
        self.subtitle.setText(f"Started {session['started_at']} · {operator}")
        self.notes_edit.setPlainText(session["notes"] or "")
        self.refresh()

    def refresh(self):
        if self.session_id is None:
            return
        for key, tile in self.tiles.items():
            run = self.db.latest_run_for_modality(self.session_id, key)
            if run is None:
                continue
            modality = modalities.get(key)
            metrics = self.db.run_metrics(run)
            tile.update_from_run(run, modality.format_metrics(metrics))

    def _run_modality(self, key):
        modality = modalities.get(key)
        if modality is None or self.session_id is None:
            return
        if key == "speech":
            modality = self._choose_speech_assessment()
            if modality is None:
                return
        analyze_existing = (
            key == "speech"
            and bool(modality.args)
            and modality.args[0].startswith("analyze-")
        )
        dlg = AssessmentRunner(
            modality, self.db, self.session_id, self,
            auto_start=analyze_existing,
        )
        dlg.exec_()
        self.refresh()

    def _choose_speech_assessment(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Speech analysis")
        dialog.setModal(True)
        dialog.resize(560, 440)
        layout = QVBoxLayout(dialog)

        title = QLabel("Choose speech analysis")
        title.setObjectName("H1")
        layout.addWidget(title)

        description = QLabel(
            "Record a new task or analyze an existing 16-bit PCM WAV file."
        )
        description.setObjectName("Dim")
        description.setWordWrap(True)
        layout.addWidget(description)

        selected = {"modality": None}

        def choose_task(task):
            selected["modality"] = modalities.speech_modality(task)
            dialog.accept()

        task_buttons = (
            ("Connected-speech assessment", "connected_speech"),
            ("Sustained-vowel assessment", "sustained_vowel"),
            ("Reading assessment", "reading"),
        )
        for label, task in task_buttons:
            button = QPushButton(label)
            button.setMinimumHeight(config.TOUCH_MIN_BUTTON_HEIGHT)
            button.clicked.connect(lambda checked=False, value=task: choose_task(value))
            layout.addWidget(button)

        def choose_existing():
            path, _ = QFileDialog.getOpenFileName(
                dialog, "Select speech recording", "", "WAV audio (*.wav)"
            )
            if not path:
                return
            labels = ["Connected speech", "Sustained vowel", "Reading"]
            label, accepted = QInputDialog.getItem(
                dialog, "Analysis type", "Recording task:", labels, 0, False
            )
            if not accepted:
                return
            tasks = {
                "Connected speech": "connected_speech",
                "Sustained vowel": "sustained_vowel",
                "Reading": "reading",
            }
            selected["modality"] = modalities.speech_modality(tasks[label], path)
            dialog.accept()

        existing_btn = QPushButton("Analyze existing WAV")
        existing_btn.setObjectName("Primary")
        existing_btn.setMinimumHeight(config.TOUCH_MIN_BUTTON_HEIGHT)
        existing_btn.clicked.connect(choose_existing)
        layout.addWidget(existing_btn)
        layout.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dialog.reject)
        layout.addWidget(cancel_btn)

        if dialog.exec_() != QDialog.Accepted:
            return None
        return selected["modality"]

    def _show_modality_details(self, key):
        if self.session_id is None:
            return
        run = self.db.latest_run_for_modality(self.session_id, key)
        modality = modalities.get(key)
        if run is None or modality is None:
            return
        show_metrics_dialog(self, modality.name, self.db.run_metrics(run))

    def _show_all_results(self):
        if self.session_id is not None:
            show_session_results_dialog(self, self.db, self.session_id)

    def _generate_report(self):
        if self.session_id is None:
            return
        try:
            path = report.write_session_report(self.db, self.session_id)
        except Exception as e:
            QMessageBox.critical(self, "Report error", f"Could not generate report:\n{e}")
            return
        if not _open_file(path):
            QMessageBox.information(
                self, "Report generated",
                f"The report was saved but could not be opened automatically:\n{path}"
            )

    def _end_session(self):
        if self.session_id is None:
            return
        reply = QMessageBox.question(
            self, "End session",
            "End this session? Recorded results are kept; no further assessments "
            "can be added to it.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self.db.end_session(self.session_id, self.notes_edit.toPlainText().strip())
        except Exception as e:
            QMessageBox.critical(self, "Database error", str(e))
            return
        self.session_id = None
        self.session_ended.emit()


# ===========================================================================
# HISTORY
# ===========================================================================

class HistoryScreen(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        title = QLabel("Session history")
        title.setObjectName("H1")
        layout.addWidget(title)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["Session", "Participant", "Started", "Status", "Assessments"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        btn_row = QHBoxLayout()
        view_btn = QPushButton("View report")
        view_btn.clicked.connect(self._view_report)
        results_btn = QPushButton("View assessments")
        results_btn.clicked.connect(self._view_assessments)
        export_btn = QPushButton("Export raw data folder path")
        export_btn.clicked.connect(self._show_raw_path)
        btn_row.addWidget(view_btn)
        btn_row.addWidget(results_btn)
        btn_row.addWidget(export_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def refresh(self):
        rows = self.db.list_sessions()
        self.table.setRowCount(len(rows))
        for i, row in enumerate(rows):
            runs = self.db.list_runs(row["id"])
            completed = sum(1 for r in runs if r["status"] == "completed")
            values = [
                str(row["id"]),
                row["participant_code"],
                row["started_at"],
                "Ended" if row["ended_at"] else "In progress",
                f"{completed}/{len(runs)} completed",
            ]
            for j, v in enumerate(values):
                item = QTableWidgetItem(v)
                if j == 0:
                    item.setData(Qt.UserRole, row["id"])
                self.table.setItem(i, j, item)

    def _selected_session_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item else None

    def _view_report(self):
        sid = self._selected_session_id()
        if sid is None:
            QMessageBox.information(self, "No selection", "Select a session first.")
            return
        try:
            path = report.write_session_report(self.db, sid)
        except Exception as e:
            QMessageBox.critical(self, "Report error", str(e))
            return
        if not _open_file(path):
            QMessageBox.information(
                self, "Report generated",
                f"The report was saved but could not be opened automatically:\n{path}"
            )

    def _view_assessments(self):
        sid = self._selected_session_id()
        if sid is None:
            QMessageBox.information(self, "No selection", "Select a session first.")
            return
        show_session_results_dialog(self, self.db, sid)

    def _show_raw_path(self):
        sid = self._selected_session_id()
        if sid is None:
            QMessageBox.information(self, "No selection", "Select a session first.")
            return
        path = self.db.session_raw_dir(sid)
        QMessageBox.information(self, "Raw data location", path)


# ===========================================================================
# SYSTEM CHECK
# ===========================================================================

def _detect_microphone():
    """Return (expected, status, ok) for an input-capable audio device."""
    try:
        import sounddevice as sd

        devices = sd.query_devices()
        inputs = [(index, device) for index, device in enumerate(devices)
                  if int(device.get("max_input_channels", 0)) > 0]
        if not inputs:
            return "Input-capable audio device", "No microphone detected", False

        try:
            default_index = int(sd.default.device[0])
        except (AttributeError, IndexError, TypeError, ValueError):
            default_index = -1
        selected = next((item for item in inputs if item[0] == default_index),
                        inputs[0])
        index, device = selected
        name = str(device.get("name") or f"Device {index}")
        channels = int(device.get("max_input_channels", 0))
        suffix = " (default)" if index == default_index else ""
        return ("Input-capable audio device",
                f"{name} - {channels} input channel(s){suffix}", True)
    except Exception:
        arecord = shutil.which("arecord")
        if arecord:
            try:
                result = subprocess.run(
                    [arecord, "-l"], capture_output=True, text=True,
                    check=False, timeout=5,
                )
                cards = [line for line in result.stdout.splitlines()
                         if line.lstrip().startswith("card ")]
                if result.returncode == 0 and cards:
                    return ("Input-capable audio device",
                            f"{len(cards)} ALSA capture device(s) detected", True)
                return ("Input-capable audio device",
                        "No ALSA microphone detected", False)
            except (OSError, subprocess.SubprocessError):
                pass
        return ("Input-capable audio device",
                "Audio detection unavailable (install sounddevice)", False)

class SystemCheckScreen(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("System check")
        title.setObjectName("H1")
        header.addWidget(title)
        header.addStretch()
        refresh_btn = QPushButton("Re-check")
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)
        layout.addLayout(header)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Item", "Expected", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table, 1)

        note = QLabel(
            "Device checks confirm availability and enumeration, not recording quality. "
            "Run each assessment's own test for a functional check."
        )
        note.setObjectName("Notice")
        note.setWordWrap(True)
        layout.addWidget(note)

    def refresh(self):
        entries = []

        for modality in modalities.REGISTRY:
            ok = modality.is_available()
            entries.append((
                f"{modality.name} program",
                modality.script_path or "(not set)",
                "Found" if ok else "Missing",
                ok,
            ))

        for label, path in config.DEVICE_CHECKS.items():
            ok = os.path.exists(path)
            entries.append((label, path, "Present" if ok else "Not detected", ok))

        mic_expected, mic_status, mic_ok = _detect_microphone()
        entries.append(("Microphone input", mic_expected, mic_status, mic_ok))

        for label, path in (("Data directory", config.DATA_DIR),
                            ("Database", config.DB_PATH),
                            ("Report directory", config.REPORT_DIR)):
            ok = os.path.exists(path)
            entries.append((label, path, "OK" if ok else "Missing", ok))

        try:
            usage = shutil.disk_usage(config.DATA_DIR)
            free_gb = usage.free / (1024 ** 3)
            entries.append((
                "Free disk space", "> 1 GB recommended",
                f"{free_gb:.1f} GB free", free_gb > 1.0,
            ))
        except OSError:
            entries.append(("Free disk space", "—", "Unavailable", False))

        self.table.setRowCount(len(entries))
        for i, (item, expected, status, ok) in enumerate(entries):
            self.table.setItem(i, 0, QTableWidgetItem(item))
            self.table.setItem(i, 1, QTableWidgetItem(expected))
            status_item = QTableWidgetItem(status)
            status_item.setForeground(Qt.green if ok else Qt.red)
            self.table.setItem(i, 2, status_item)


# ===========================================================================
# helpers
# ===========================================================================

def _open_file(path):
    """Open a generated file with the desktop default handler."""
    return QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.abspath(path)))
