"""
NEXA UI - Assessment runner

Three-phase dialog that wraps an existing modality program:

    1. PREPARE  - operator checklist + large patient-facing instruction
    2. RUNNING  - launches the modality script via QProcess, live stdout log,
                  elapsed timer, abort control
    3. REVIEW   - parsed summary metrics, operator notes, save / discard / retry

The modality program is launched unmodified. Its stdout/stderr is mirrored
into the log pane; its output files are copied into the session's raw folder.
"""

import json
import math
import os
import shutil
import time
from datetime import datetime

from PyQt5.QtCore import Qt, QProcess, QProcessEnvironment, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit,
    QFrame, QGridLayout, QLineEdit, QMessageBox, QStackedWidget, QWidget,
    QProgressBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QScrollArea,
)

import config
import theme


PHASE_PREPARE, PHASE_RUNNING, PHASE_REVIEW = 0, 1, 2


class AssessmentRunner(QDialog):
    def __init__(self, modality, db, session_id, parent=None, auto_start=False):
        super().__init__(parent)
        self.modality = modality
        self.db = db
        self.session_id = session_id

        self.process = None
        self.started_at = None
        self.start_perf = None
        self.exit_code = None
        self.status = "aborted"
        self.metrics = {}
        self.saved_run_id = None
        self.copied_files = []
        self.run_output_dir = None
        self.stop_request_path = None
        self.pause_request_path = None
        self.speech_paused = False
        self.pause_started_at = None
        self.paused_total = 0.0
        self.speech_quiet_since = None

        self.setWindowTitle(f"NEXA — {modality.name}")
        self.setModal(True)
        if parent is not None:
            self.resize(parent.size())
        else:
            self.resize(config.SCREEN_WIDTH, config.SCREEN_HEIGHT)
        if config.FULLSCREEN:
            self.showFullScreen()

        self._build_ui()
        self.stack.setCurrentIndex(PHASE_PREPARE)

        self.elapsed_timer = QTimer(self)
        self.elapsed_timer.setInterval(200)
        self.elapsed_timer.timeout.connect(self._tick)
        if auto_start:
            QTimer.singleShot(0, self._start_run)

    # -- UI construction -------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = QFrame()
        header.setObjectName("Card")
        hl = QHBoxLayout(header)
        title = QLabel(self.modality.name)
        title.setObjectName("H1")
        subtitle = QLabel(self.modality.subtitle)
        subtitle.setObjectName("Dim")
        tbox = QVBoxLayout()
        tbox.addWidget(title)
        tbox.addWidget(subtitle)
        hl.addLayout(tbox)
        hl.addStretch()
        root.addWidget(header)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_prepare_page())
        self.stack.addWidget(self._build_running_page())
        self.stack.addWidget(self._build_review_page())
        root.addWidget(self.stack, 1)

    def _build_prepare_page(self):
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(16)

        # Operator side
        op_card = QFrame()
        op_card.setObjectName("Card")
        op_layout = QVBoxLayout(op_card)
        op_title = QLabel("Operator checklist")
        op_title.setObjectName("H2")
        op_layout.addWidget(op_title)
        for item in self.modality.operator_checklist:
            lbl = QLabel(f"•  {item}")
            lbl.setWordWrap(True)
            op_layout.addWidget(lbl)
        op_layout.addStretch()

        avail = QLabel()
        avail.setWordWrap(True)
        if self.modality.is_available():
            avail.setText(f"Program: {self.modality.script_path}")
            avail.setObjectName("Dim")
        else:
            avail.setText(
                f"NOT CONFIGURED — no script found at:\n{self.modality.script_path}\n"
                "Check config.MODALITY_MODULES and the src package."
            )
            avail.setStyleSheet(f"color: {theme.ERROR};")
        op_layout.addWidget(avail)
        layout.addWidget(op_card, 1)

        # Patient side
        pt_card = QFrame()
        pt_card.setObjectName("Card")
        pt_layout = QVBoxLayout(pt_card)
        pt_title = QLabel("Tell the participant")
        pt_title.setObjectName("H2")
        pt_layout.addWidget(pt_title)

        instruction = QLabel(self.modality.patient_instruction)
        instruction.setObjectName("Instruction")
        instruction.setWordWrap(True)
        instruction.setAlignment(Qt.AlignCenter)
        pt_layout.addWidget(instruction)

        detail = QLabel(self.modality.patient_detail)
        detail.setWordWrap(True)
        detail.setAlignment(Qt.AlignCenter)
        pt_layout.addWidget(detail)
        pt_layout.addStretch()

        est = QLabel(f"Estimated duration: ~{self.modality.est_duration_s} s")
        est.setObjectName("Dim")
        est.setAlignment(Qt.AlignCenter)
        pt_layout.addWidget(est)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        self.start_btn = QPushButton("Start assessment")
        self.start_btn.setObjectName("Primary")
        self.start_btn.setEnabled(self.modality.is_available())
        self.start_btn.clicked.connect(self._start_run)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self.start_btn, 2)
        pt_layout.addLayout(btn_row)

        layout.addWidget(pt_card, 1)
        return page

    def _build_running_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        status_card = QFrame()
        status_card.setObjectName("Card")
        sl = QHBoxLayout(status_card)
        self.running_label = QLabel("Assessment running…")
        self.running_label.setObjectName("H2")
        self.elapsed_label = QLabel(
            f"{math.ceil(self.modality.est_duration_s)} s"
        )
        self.elapsed_label.setObjectName("Metric")
        sl.addWidget(self.running_label)
        sl.addStretch()
        sl.addWidget(self.elapsed_label)
        layout.addWidget(status_card)

        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)

        recording_speech = (self.modality.key == "speech" and
                            bool(self.modality.args) and
                            self.modality.args[0] == "assess")
        self.audio_level_label = QLabel(
            "Listening for the participant's voice...")
        self.audio_level_label.setObjectName("Notice")
        self.audio_level_label.setWordWrap(True)
        self.audio_level_label.setVisible(recording_speech)
        layout.addWidget(self.audio_level_label)
        self.audio_meter = QProgressBar()
        self.audio_meter.setRange(0, 1000)
        self.audio_meter.setValue(0)
        self.audio_meter.setTextVisible(False)
        self.audio_meter.setFixedHeight(12)
        self.audio_meter.setVisible(recording_speech)
        layout.addWidget(self.audio_meter)
        self.pause_feedback_label = QLabel(
            "Live pause feedback starts when low input persists.")
        self.pause_feedback_label.setObjectName("Notice")
        self.pause_feedback_label.setVisible(recording_speech)
        layout.addWidget(self.pause_feedback_label)
        note = QLabel(
            "Pause and resume as needed. Select End recording and analyze "
            "when the participant finishes, or allow the timer to end normally."
            if recording_speech else
            "The assessment program controls the display while it runs. "
            "Do not interact with this screen unless you need to abort."
        )
        note.setObjectName("Dim")
        note.setWordWrap(True)
        if not self.modality.passage_text:
            layout.addWidget(note)
        else:
            passage = QLabel(self.modality.passage_text)
            passage.setObjectName("Passage")
            passage.setTextFormat(Qt.PlainText)
            passage.setWordWrap(True)
            passage.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            passage.setMargin(12)
            passage_scroll = QScrollArea()
            passage_scroll.setWidgetResizable(True)
            passage_scroll.setWidget(passage)
            layout.addWidget(passage_scroll, 1)

        self.log = QPlainTextEdit()
        self.log.setObjectName("Log")
        self.log.setReadOnly(True)
        if self.modality.passage_text:
            self.log.setMaximumHeight(65)
        layout.addWidget(self.log, 1)

        controls = QHBoxLayout()
        self.pause_speech_btn = QPushButton("Pause recording")
        self.pause_speech_btn.setVisible(recording_speech)
        self.pause_speech_btn.clicked.connect(self._toggle_speech_pause)
        controls.addWidget(self.pause_speech_btn)
        self.finish_speech_btn = QPushButton("End recording and analyze")
        self.finish_speech_btn.setObjectName("Primary")
        self.finish_speech_btn.setVisible(recording_speech)
        self.finish_speech_btn.clicked.connect(self._finish_speech_early)
        controls.addWidget(self.finish_speech_btn)
        abort_btn = QPushButton("Abort assessment")
        abort_btn.setObjectName("Danger")
        abort_btn.clicked.connect(self._abort_run)
        controls.addWidget(abort_btn)
        layout.addLayout(controls)
        return page

    def _build_review_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.review_status = QLabel()
        self.review_status.setObjectName("H2")
        layout.addWidget(self.review_status)
        self.analysis_warning = QLabel()
        self.analysis_warning.setWordWrap(True)
        self.analysis_warning.setVisible(False)
        layout.addWidget(self.analysis_warning)

        metrics_card = QFrame()
        metrics_card.setObjectName("Card")
        self.metrics_grid = QGridLayout(metrics_card)
        self.metrics_grid.setContentsMargins(18, 18, 18, 18)
        layout.addWidget(metrics_card)

        files_row = QHBoxLayout()
        self.files_label = QLabel()
        self.files_label.setObjectName("Dim")
        self.files_label.setWordWrap(True)
        files_row.addWidget(self.files_label, 1)
        self.details_btn = QPushButton("Show details")
        self.details_btn.setEnabled(False)
        self.details_btn.clicked.connect(self._show_details)
        files_row.addWidget(self.details_btn)
        self.analysis_btn = QPushButton("Show analysis")
        self.analysis_btn.setVisible(self.modality.key == "motor")
        self.analysis_btn.setEnabled(False)
        self.analysis_btn.clicked.connect(self._show_analysis)
        files_row.addWidget(self.analysis_btn)
        layout.addLayout(files_row)

        layout.addWidget(QLabel("Operator notes (optional)"))
        self.notes_edit = QLineEdit()
        self.notes_edit.setPlaceholderText(
            "e.g. participant blinked frequently; second attempt after repositioning"
        )
        layout.addWidget(self.notes_edit)
        layout.addStretch()

        btn_row = QHBoxLayout()
        discard_btn = QPushButton("Discard")
        discard_btn.clicked.connect(self._discard)
        retry_btn = QPushButton("Retry assessment")
        retry_btn.clicked.connect(self._retry)
        save_btn = QPushButton("Save to session")
        save_btn.setObjectName("Primary")
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(discard_btn)
        btn_row.addWidget(retry_btn)
        btn_row.addWidget(save_btn, 2)
        layout.addLayout(btn_row)
        return page

    # -- run control -------------------------------------------------------

    def _start_run(self):
        if not self.modality.is_available():
            QMessageBox.warning(self, "Not configured",
                                "The modality package was not found. Check config.MODALITY_MODULES.")
            return

        self.log.clear()
        self.metrics = {}
        self.copied_files = []
        self.started_at = datetime.now().isoformat(timespec="seconds")
        self.start_perf = time.perf_counter()
        self.status = "running"
        self.elapsed_label.setText(
            f"{math.ceil(self.modality.est_duration_s)} s"
        )
        self.progress.setValue(0)
        config.ensure_dirs()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.run_output_dir = os.path.join(
            config.RUN_STAGING_DIR, f"{self.modality.key}_{stamp}")
        os.makedirs(self.run_output_dir, exist_ok=True)
        self.stop_request_path = os.path.join(
            self.run_output_dir, "stop_recording.request")
        self.pause_request_path = os.path.join(
            self.run_output_dir, "pause_recording.request")
        self.speech_paused = False
        self.pause_started_at = None
        self.paused_total = 0.0
        self.speech_quiet_since = None
        self.audio_level_label.setText(
            "Listening for the participant's voice...")
        self.audio_level_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
        self.audio_meter.setValue(0)
        self.pause_feedback_label.setText(
            "Live pause feedback starts when low input persists.")
        self.pause_feedback_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
        self.pause_speech_btn.setEnabled(True)
        self.pause_speech_btn.setText("Pause recording")
        self.finish_speech_btn.setEnabled(True)
        self.finish_speech_btn.setText("End recording and analyze")

        cmd = self.modality.build_command()
        self._append_log(f"$ {' '.join(cmd)}")

        self.process = QProcess(self)
        environment = QProcessEnvironment.systemEnvironment()
        old_pythonpath = environment.value("PYTHONPATH")
        pythonpath = config.SOURCE_DIR
        if old_pythonpath:
            pythonpath += os.pathsep + old_pythonpath
        environment.insert("PYTHONPATH", pythonpath)
        environment.insert("NEXA_OUTPUT_DIR", self.run_output_dir)
        environment.insert("NEXA_STOP_REQUEST", self.stop_request_path)
        environment.insert("NEXA_PAUSE_REQUEST", self.pause_request_path)
        environment.insert("NEXA_SESSION_ID", str(self.session_id))
        session = self.db.get_session(self.session_id)
        if session is not None:
            participant = self.db.get_participant(session["participant_id"])
            if participant is not None:
                environment.insert("NEXA_PARTICIPANT_ID", participant["code"])
        self.process.setProcessEnvironment(environment)
        self.process.setWorkingDirectory(self.modality.working_dir)
        self.process.setProcessChannelMode(QProcess.MergedChannels)
        self.process.readyReadStandardOutput.connect(self._read_output)
        self.process.finished.connect(self._on_finished)
        self.process.errorOccurred.connect(self._on_process_error)

        self.stack.setCurrentIndex(PHASE_RUNNING)
        self.elapsed_timer.start()
        self.process.start(cmd[0], cmd[1:])

        if not self.process.waitForStarted(5000):
            self._append_log("ERROR: failed to start the modality program.")
            self.status = "failed"
            self._enter_review()

    def _tick(self):
        if self.start_perf is None:
            return
        now = time.perf_counter()
        wall_elapsed = now - self.start_perf
        current_pause = ((now - self.pause_started_at)
                         if self.speech_paused and self.pause_started_at else 0.0)
        elapsed = max(0.0, wall_elapsed - self.paused_total - current_pause)
        estimate = max(float(self.modality.est_duration_s), 0.1)
        remaining = max(0, math.ceil(estimate - elapsed))
        if self.speech_paused:
            self.elapsed_label.setText(f"Paused | {remaining} s")
        else:
            self.elapsed_label.setText(f"{remaining} s" if remaining else "Finishing...")
        self.progress.setValue(min(1000, round(1000 * elapsed / estimate)))
        if wall_elapsed > config.MODALITY_TIMEOUT_S:
            self._append_log(
                f"ERROR: exceeded MODALITY_TIMEOUT_S ({config.MODALITY_TIMEOUT_S}s); terminating."
            )
            self.status = "failed"
            self._kill_process()

    def _read_output(self):
        if self.process is None:
            return
        data = bytes(self.process.readAllStandardOutput()).decode("utf-8", errors="replace")
        for line in data.splitlines():
            if line.startswith("[audio-level]"):
                self._update_speech_audio_level(line)
                continue
            self._append_log(line)
            if (self.modality.key == "speech" and
                    line.startswith("Recording saved:")):
                self.finish_speech_btn.setEnabled(False)
                self.finish_speech_btn.setText("Recording complete")
                self.pause_speech_btn.setEnabled(False)
                self.running_label.setText("Analyzing speech...")
                self.audio_level_label.setText("Recording complete")
                self.pause_feedback_label.setText(
                    "Final pauses are being calculated with Praat...")

    def _update_speech_audio_level(self, line):
        parts = line.split()
        if len(parts) < 3:
            return
        try:
            dbfs = float(parts[1])
        except ValueError:
            return
        meter_value = round(1000 * (dbfs + 60.0) / 50.0)
        self.audio_meter.setValue(max(0, min(1000, meter_value)))
        if parts[2] == "quiet":
            now = time.perf_counter()
            if self.speech_quiet_since is None:
                self.speech_quiet_since = now
            quiet_duration = now - self.speech_quiet_since
            if quiet_duration >= 0.3:
                self.pause_feedback_label.setText(
                    "Possible pause: %.1f s (live level estimate)" %
                    quiet_duration)
                self.pause_feedback_label.setStyleSheet(
                    f"color: {theme.WARN};")
            if now - self.speech_quiet_since >= 1.5:
                self.audio_level_label.setText(
                    "Audio is too quiet. Move closer, speak louder, or check "
                    "the selected microphone. (%0.1f dBFS)" % dbfs)
                self.audio_level_label.setStyleSheet(
                    f"color: {theme.WARN}; font-weight: bold;")
            return
        self.speech_quiet_since = None
        self.pause_feedback_label.setText("Speech level detected")
        self.pause_feedback_label.setStyleSheet(f"color: {theme.OK};")
        self.audio_level_label.setText(
            "Microphone level detected (%0.1f dBFS)" % dbfs)
        self.audio_level_label.setStyleSheet(f"color: {theme.OK};")

    def _append_log(self, text):
        self.log.appendPlainText(text)
        doc = self.log.document()
        if doc.blockCount() > config.LOG_TAIL_LINES:
            cursor = self.log.textCursor()
            cursor.movePosition(cursor.Start)
            for _ in range(doc.blockCount() - config.LOG_TAIL_LINES):
                cursor.select(cursor.BlockUnderCursor)
                cursor.removeSelectedText()
                cursor.deleteChar()

    def _on_process_error(self, err):
        self._append_log(f"ERROR: process error ({int(err)}).")
        self.status = "failed"

    def _abort_run(self):
        reply = QMessageBox.question(
            self, "Abort assessment",
            "Stop the running assessment? Partial data may still be saved.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.status = "aborted"
            self._kill_process()

    def _finish_speech_early(self):
        if (self.modality.key != "speech" or not self.stop_request_path or
                self.process is None or
                self.process.state() == QProcess.NotRunning):
            return
        was_paused = self.speech_paused
        if not was_paused and not self._set_speech_paused(True):
            return
        reply = QMessageBox.question(
            self, "End speech recording",
            "End the recording now and analyze the audio captured so far?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            if not was_paused:
                self._set_speech_paused(False)
            return
        try:
            with open(self.stop_request_path, "w", encoding="ascii") as handle:
                handle.write("stop\n")
        except OSError as exc:
            QMessageBox.warning(
                self, "Could not end recording",
                "The stop request could not be written:\n%s" % exc)
            if not was_paused:
                self._set_speech_paused(False)
            return
        self.finish_speech_btn.setEnabled(False)
        self.finish_speech_btn.setText("Finishing recording...")
        self.pause_speech_btn.setEnabled(False)
        self.running_label.setText("Finishing and analyzing speech...")
        self._append_log("--- early recording finish requested ---")

    def _toggle_speech_pause(self):
        if (self.modality.key != "speech" or not self.pause_request_path or
                self.process is None or
                self.process.state() == QProcess.NotRunning):
            return
        self._set_speech_paused(not self.speech_paused)

    def _set_speech_paused(self, paused):
        """Set the speech recorder pause request and mirror it in the UI."""
        if paused == self.speech_paused:
            return True
        if not paused:
            try:
                if os.path.exists(self.pause_request_path):
                    os.remove(self.pause_request_path)
            except OSError as exc:
                QMessageBox.warning(
                    self, "Could not resume recording",
                    "The pause request could not be removed:\n%s" % exc)
                return False
            now = time.perf_counter()
            if self.pause_started_at is not None:
                self.paused_total += now - self.pause_started_at
            self.pause_started_at = None
            self.speech_paused = False
            self.pause_speech_btn.setText("Pause recording")
            self.running_label.setText("Assessment running...")
            self.speech_quiet_since = None
            self.audio_level_label.setText(
                "Listening for the participant's voice...")
            self.audio_level_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
            self.pause_feedback_label.setText(
                "Live pause feedback starts when low input persists.")
            self.pause_feedback_label.setStyleSheet(
                f"color: {theme.TEXT_DIM};")
            self._append_log("--- speech recording resumed ---")
            return True
        try:
            with open(self.pause_request_path, "w", encoding="ascii") as handle:
                handle.write("pause\n")
        except OSError as exc:
            QMessageBox.warning(
                self, "Could not pause recording",
                "The pause request could not be written:\n%s" % exc)
            return False
        self.speech_paused = True
        self.pause_started_at = time.perf_counter()
        self.pause_speech_btn.setText("Resume recording")
        self.running_label.setText("Speech recording paused")
        self.speech_quiet_since = None
        self.audio_level_label.setText("Microphone monitoring paused")
        self.audio_level_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
        self.pause_feedback_label.setText("Pause feedback paused")
        self.pause_feedback_label.setStyleSheet(f"color: {theme.TEXT_DIM};")
        self._append_log("--- speech recording paused ---")
        return True

    def _kill_process(self):
        if self.process is not None and self.process.state() != QProcess.NotRunning:
            self.process.terminate()
            if not self.process.waitForFinished(3000):
                self.process.kill()
                self.process.waitForFinished(2000)

    def _on_finished(self, exit_code, exit_status):
        self.elapsed_timer.stop()
        self.exit_code = exit_code
        self._read_output()
        self._append_log(f"--- program exited with code {exit_code} ---")

        if self.status not in ("aborted", "failed"):
            self.status = "completed" if exit_code == 0 else "failed"
        self._enter_review()

    # -- review -------------------------------------------------------

    def _enter_review(self):
        self.elapsed_timer.stop()

        output_paths = self.modality.collect_output_files(self.run_output_dir)
        self.metrics = self.modality.parse_metrics(output_paths)
        self._pending_output_paths = output_paths

        colour = {"completed": theme.OK, "aborted": theme.WARN, "failed": theme.ERROR}
        label = {"completed": "Assessment complete",
                 "aborted": "Assessment aborted",
                 "failed": "Assessment failed"}
        self.review_status.setText(label.get(self.status, self.status))
        self.review_status.setStyleSheet(f"color: {colour.get(self.status, theme.TEXT)};")
        self.analysis_warning.setVisible(False)
        if self.modality.key == "speech":
            timing = self.metrics.get("analysis_parameters", {}).get(
                "speech_timing", {})
            if timing.get("method") != "praat_sound_to_textgrid_silences":
                error = timing.get("error", timing.get("status", "unknown error"))
                self.analysis_warning.setText(
                    "Praat pause analysis was unavailable; pause results use "
                    "the RMS fallback and are not directly comparable. %s" % error)
                self.analysis_warning.setStyleSheet(
                    f"color: {theme.WARN}; font-weight: bold;")
                self.analysis_warning.setVisible(True)

        # Clear and repopulate metrics grid
        while self.metrics_grid.count():
            item = self.metrics_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        formatted = self.modality.format_metrics(self.metrics)
        if not formatted or all(v == "—" for _, v in formatted):
            empty = QLabel("No summary metrics could be read from the output files.")
            empty.setObjectName("Dim")
            self.metrics_grid.addWidget(empty, 0, 0)
        else:
            for i, (label_text, value_text) in enumerate(formatted):
                col = i % 4
                row = (i // 4) * 2
                value_lbl = QLabel(value_text)
                value_lbl.setObjectName("Metric")
                name_lbl = QLabel(label_text)
                name_lbl.setObjectName("MetricLabel")
                self.metrics_grid.addWidget(value_lbl, row, col)
                self.metrics_grid.addWidget(name_lbl, row + 1, col)

        if output_paths:
            names = ", ".join(os.path.basename(p) for p in output_paths)
            self.files_label.setText(f"Output files found: {names}")
        else:
            self.files_label.setText(
                "No output files found. Check that the modality program's output "
                "filenames match modalities.py."
            )
        self.details_btn.setEnabled(bool(self.metrics))
        analysis_files = {"motor": "shoulder_analysis.png",
                          "speech": "speech_analysis.png"}
        analysis_name = analysis_files.get(self.modality.key)
        self.analysis_btn.setVisible(analysis_name is not None)
        self.analysis_btn.setEnabled(bool(analysis_name) and any(
            os.path.basename(path) == analysis_name for path in output_paths))

        self.stack.setCurrentIndex(PHASE_REVIEW)

    def _show_analysis(self):
        analysis_files = {"motor": ("shoulder_analysis.png",
                                    "Shoulder velocity analysis"),
                          "speech": ("speech_analysis.png",
                                     "Speech volume and pause analysis")}
        analysis = analysis_files.get(self.modality.key)
        if analysis is None:
            return
        filename, title = analysis
        path = next((path for path in getattr(self, "_pending_output_paths", [])
                     if os.path.basename(path) == filename), None)
        if not path:
            return
        pixmap = QPixmap(path)
        if pixmap.isNull():
            QMessageBox.warning(self, "Analysis unavailable", "Could not load the velocity plot.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)
        plot = QLabel()
        plot.setPixmap(pixmap.scaled(config.SCREEN_WIDTH - 80,
                                    config.SCREEN_HEIGHT - 120,
                                    Qt.KeepAspectRatio, Qt.SmoothTransformation))
        layout.addWidget(plot)
        close = QPushButton("Close")
        close.clicked.connect(dialog.accept)
        layout.addWidget(close)
        dialog.exec_()

    def _show_details(self):
        """Show every metric returned by the modality analysis."""
        if not self.metrics:
            return

        dialog = QDialog(self)
        dialog.setWindowTitle(f"{self.modality.name} analysis details")
        dialog.resize(min(760, config.SCREEN_WIDTH - 40),
                      min(520, config.SCREEN_HEIGHT - 40))
        layout = QVBoxLayout(dialog)

        title = QLabel("Analysis details")
        title.setObjectName("H2")
        layout.addWidget(title)

        table = QTableWidget(len(self.metrics), 2, dialog)
        table.setHorizontalHeaderLabels(["Measurement", "Value"])
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setAlternatingRowColors(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        for row, (key, value) in enumerate(sorted(self.metrics.items())):
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

        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dialog.accept)
        layout.addWidget(close_btn)
        dialog.exec_()

    def _copy_raw_files(self):
        """Copy the modality's output into this session's raw folder."""
        session_dir = self.db.session_raw_dir(self.session_id)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = os.path.join(session_dir, f"{self.modality.key}_{stamp}")
        try:
            os.makedirs(run_dir, exist_ok=True)
            for path in getattr(self, "_pending_output_paths", []):
                shutil.copy2(path, os.path.join(run_dir, os.path.basename(path)))
            # Preserve the run log alongside the data.
            with open(os.path.join(run_dir, "run_log.txt"), "w") as f:
                f.write(self.log.toPlainText())
            self._cleanup_staging()
            return run_dir
        except OSError as e:
            QMessageBox.warning(self, "Storage error",
                                f"Could not copy raw output files:\n{e}")
            return ""

    def _save(self):
        raw_path = self._copy_raw_files()
        try:
            self.saved_run_id = self.db.record_run(
                session_id=self.session_id,
                modality=self.modality.key,
                started_at=self.started_at,
                status=self.status,
                exit_code=self.exit_code,
                metrics=self.metrics,
                raw_path=raw_path,
                operator_notes=self.notes_edit.text().strip(),
            )
        except Exception as e:
            QMessageBox.critical(self, "Database error",
                                 f"Could not save the run:\n{e}")
            return
        self.accept()

    def _discard(self):
        reply = QMessageBox.question(
            self, "Discard result",
            "Discard this run? It will not be stored in the session record.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._cleanup_staging()
            self.reject()

    def _retry(self):
        self._cleanup_staging()
        self.status = "aborted"
        self.exit_code = None
        self.stack.setCurrentIndex(PHASE_PREPARE)

    def _cleanup_staging(self):
        if self.run_output_dir and os.path.isdir(self.run_output_dir):
            try:
                shutil.rmtree(self.run_output_dir)
            except OSError:
                pass
        self.run_output_dir = None
        self.stop_request_path = None
        self.pause_request_path = None
        self.speech_paused = False
        self.pause_started_at = None
        self.paused_total = 0.0
        self.speech_quiet_since = None

    # -- cleanup -------------------------------------------------------

    def closeEvent(self, event):
        self.elapsed_timer.stop()
        self._kill_process()
        if self.saved_run_id is None:
            self._cleanup_staging()
        super().closeEvent(event)

    def keyPressEvent(self, event):
        # Block stray Escape closes while a measurement is running.
        if event.key() == Qt.Key_Escape and self.stack.currentIndex() == PHASE_RUNNING:
            return
        super().keyPressEvent(event)
