import atexit
import datetime as dt
import logging
import math
import subprocess
import sys
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

import bitmath
from PySide6.QtCore import (QByteArray, QCoreApplication, QFileInfo, QProcess,
                            QSettings, QStandardPaths, Qt, Signal)
from PySide6.QtGui import QAction, QCloseEvent, QIcon
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog,
                               QDialogButtonBox, QFileDialog, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QMainWindow, QMessageBox, QPushButton,
                               QSizePolicy, QSpinBox, QTextEdit, QVBoxLayout,
                               QWidget)

import copy_tool.rclone as rclone
import copy_tool.widgets as widgets
from copy_tool import persistence
from copy_tool._version import __version__


class ApplicationLogFilter(logging.Filter):
    allowed_names = ['CopyTool']

    def filter(self, record):
        return any(a in record.name for a in self.allowed_names)


def setup_logging(log_level=logging.INFO):
    app_dir = QStandardPaths.writableLocation(
        QStandardPaths.AppLocalDataLocation)
    log_dir = Path(app_dir) / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / 'CopyTool_log.txt'

    # Formats
    date_format = '%Y-%m-%d %H:%M:%S UTC'
    line_format = '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s'

    # Setup formatter
    logger_frmt = logging.Formatter(fmt=line_format, datefmt=date_format)
    logger_frmt.converter = time.gmtime

    # Setup log filter
    log_filter = ApplicationLogFilter()

    # Setup handlers
    handlers = []

    stderr_hndl = logging.StreamHandler()
    stderr_hndl.setLevel(log_level)
    stderr_hndl.setFormatter(logger_frmt)
    stderr_hndl.addFilter(log_filter)
    handlers.append(stderr_hndl)

    file_hndl = RotatingFileHandler(filename=log_file,
                                    maxBytes=5000000,
                                    backupCount=10)
    file_hndl.setLevel(log_level)
    file_hndl.setFormatter(logger_frmt)
    file_hndl.addFilter(log_filter)
    handlers.append(file_hndl)

    # noinspection PyArgumentList
    logging.basicConfig(format=line_format, level=log_level,
                        datefmt=date_format, handlers=handlers)


def app_icon_path():
    """Return the path to the app icon if app is bundled or running from the
    source code directory.
    """
    if hasattr(sys, '_MEIPASS'):
        d = ''
    else:
        d = str(Path(__file__).resolve().parent / 'assets')

    if sys.platform == 'win32':
        d = f'{d}\\' if len(d) else f'{str(Path(sys._MEIPASS).resolve())}\\'
        f = 'icon.ico'
    elif sys.platform == 'darwin':
        d = f'{d}/' if len(d) else '../Resources/'
        f = 'icon.icns'
    elif sys.platform == 'linux':
        d = f'{d}/' if len(d) else f'{str(Path(sys._MEIPASS).resolve())}/'
        f = 'icon-linux.ico'
    else:
        d = f'{d}/' if len(d) else ''
        f = 'icon-round.png'
    return f'{d}{f}'


class MainWindow(QMainWindow):
    _rclone = None
    _start_time = None
    _logger = None

    advance_queue = Signal()

    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent=parent)

        self._logger = logging.getLogger('CopyTool')

        # Check for rclone
        if not rclone.is_installed():
            self._logger.error('rclone not detected')
            error_box = QMessageBox()
            error_box.setWindowTitle('CopyTool')
            error_box.setIcon(QMessageBox.Critical)
            error_box.setText('rclone not detected!')
            error_box.setInformativeText(
                'Please add rclone to your system PATH and relaunch.')
            error_box.setModal(True)
            error_box.setStandardButtons(QMessageBox.Ok)
            error_box.setDefaultButton(QMessageBox.Ok)
            error_box.exec()
            sys.exit(1)

        # Settings window
        self._settings_window = SettingsWindow()

        # Menus
        self.file_menu = self.menuBar().addMenu(' &File')
        settings_action = QAction('&Preferences', self)
        settings_action.setStatusTip('Open the preferences menu')
        settings_action.triggered.connect(self._settings_window.show)
        self.file_menu.addAction(settings_action)

        self.file_menu.addSeparator()
        exit_action = QAction('&Exit', self)
        exit_action.setStatusTip('Closes the program')
        exit_action.triggered.connect(self.close)
        self.file_menu.addAction(exit_action)

        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # Cards list
        self._cards_widget = widgets.CardListWidget()
        main_layout.addWidget(self._cards_widget, stretch=2)

        self._copy_ctrls = QWidget()
        self._copy_ctrls.setLayout(QHBoxLayout())
        self._copy_ctrls.layout().setContentsMargins(5, 0, 5, 0)
        self._copy_ctrls.layout().setSpacing(5)
        self._copy_ctrls.layout().setAlignment(Qt.AlignRight)
        main_layout.addWidget(self._copy_ctrls)

        self._shutdown_opt = QCheckBox('Shutdown on complete')
        self._shutdown_opt.setChecked(False)
        # Shutdown requires elevated privileges on Unix-like systems,
        # So only add option on Windows for now
        if sys.platform == 'win32':
            self._copy_ctrls.layout().addWidget(self._shutdown_opt)
            self._copy_ctrls.layout().addSpacing(25)

        self._copy_btn = QPushButton('Start')
        # Single persistent connection; the handler branches on self._running
        # rather than swapping connections (which previously left the button
        # stuck on "Cancel" and could raise on a bare disconnect()).
        self._copy_btn.clicked.connect(self._on_copy_button)
        self._copy_ctrls.layout().addWidget(self._copy_btn, stretch=1)

        self._console = QTextEdit()
        self._console.setReadOnly(True)
        self._console.setMinimumHeight(100)
        app_str = f'{QApplication.organizationName()} ' \
                  f'{QApplication.applicationName()} ' \
                  f'v{QApplication.applicationVersion()}'
        self._console.append(f'<font color="Gray">{app_str}</font>')
        main_layout.addWidget(self._console)

        self.advance_queue.connect(self._on_advance_queue)

        self._rclone = QProcess()
        self._rclone.setProgram(rclone.executable_path())
        self._rclone.finished.connect(self._on_copy_process_exit)
        self._rclone.readyReadStandardOutput.connect(self._on_stdout_ready)
        self._rclone.readyReadStandardError.connect(self._on_stderr_ready)

        self._prescript = QProcess()
        self._prescript.finished.connect(self._on_prescript_exit)

        self._queue_canceled = False
        self._current_copy = None
        self._queue = []
        self._running = False

        self._load_settings()

    def closeEvent(self, event: QCloseEvent):
        # Confirm before tearing down an in-flight transfer.
        if self._any_process_running():
            resp = QMessageBox.question(
                self, 'CopyTool',
                'A transfer is in progress. Quit and cancel it?',
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if resp != QMessageBox.Yes:
                event.ignore()
                return

        self._logger.info('Shutting down')
        self._queue = []
        self._queue_canceled = True
        self._stop_processes()
        self._save_settings()

        # Drop the crash-handler reference so atexit doesn't hold a destroyed
        # window.
        global _active_window
        if _active_window is self:
            _active_window = None
        event.accept()

    def _any_process_running(self) -> bool:
        for proc in (self._prescript, self._rclone):
            try:
                if proc.state() != QProcess.NotRunning:
                    return True
            except RuntimeError:
                # Underlying C++ object already deleted; treat as not running.
                pass
        return False

    def _stop_processes(self):
        """Terminate (then kill) any running child processes. Safe to call
        even if the underlying C++ QProcess objects have been deleted."""
        for proc in (self._prescript, self._rclone):
            try:
                if proc.state() != QProcess.NotRunning:
                    proc.terminate()
                    if not proc.waitForFinished(5000):
                        proc.kill()
                        proc.waitForFinished(2000)
            except RuntimeError:
                pass

    def _save_settings(self):
        settings = QSettings()

        settings.setValue("mainWin/geometry", self.saveGeometry())
        settings.setValue("mainWin/state", self.saveState())
        self._write_cards(settings, self._cards_widget.card_list)

    @staticmethod
    def _write_cards(settings: QSettings, cards):
        """Persist the card list as a single JSON string (native-backend
        safe) along with the schema version."""
        settings.setValue(persistence.VERSION_KEY, persistence.SETTINGS_VERSION)
        settings.setValue(persistence.CARDS_KEY,
                          persistence.serialize_cards(cards))

    def _load_settings(self):
        settings = QSettings()
        # Restore each piece independently so one corrupt value can't take
        # down the others (or the whole startup).
        self._restore_window_geometry(settings)
        self._load_cards(settings)

    def _restore_window_geometry(self, settings: QSettings):
        try:
            geom = settings.value("mainWin/geometry")
            if isinstance(geom, QByteArray) and not geom.isEmpty():
                self.restoreGeometry(geom)
        except Exception:
            self._logger.exception('Failed to restore window geometry')
        try:
            state = settings.value("mainWin/state")
            if isinstance(state, QByteArray) and not state.isEmpty():
                self.restoreState(state)
        except Exception:
            self._logger.exception('Failed to restore window state')

    def _load_cards(self, settings: QSettings):
        """Load job cards, migrating legacy formats and recovering from any
        corrupt value. Seeds one empty card only on a true first launch."""
        first_launch = False
        try:
            if settings.contains(persistence.CARDS_KEY):
                cards = persistence.deserialize_cards(
                    settings.value(persistence.CARDS_KEY, '', type=str))
            elif (settings.contains(persistence.LEGACY_CARDS_KEY)
                  or settings.contains(persistence.LEGACY_SOURCE_KEY)
                  or settings.contains(persistence.LEGACY_TARGET_KEY)):
                cards = self._migrate_legacy_cards(settings)
            else:
                first_launch = True
                cards = []
        except Exception:
            self._logger.exception('Failed to load cards; resetting')
            if settings.contains(persistence.CARDS_KEY):
                settings.remove(persistence.CARDS_KEY)
            first_launch = True
            cards = []

        if cards:
            self._cards_widget.card_list = cards
        elif first_launch:
            # Friendly default for a brand-new install.
            self._cards_widget.add_card(widgets.CopyJobCard())
        # else: a genuinely empty saved list — respect it (just the + button).

    def _migrate_legacy_cards(self, settings: QSettings):
        """Convert pre-1.3.0 settings to the new JSON format and remove the
        legacy keys."""
        legacy_cards = settings.value(persistence.LEGACY_CARDS_KEY)
        legacy_source = (settings.value(persistence.LEGACY_SOURCE_KEY, '')
                         if settings.contains(persistence.LEGACY_SOURCE_KEY)
                         else None)
        legacy_target = (settings.value(persistence.LEGACY_TARGET_KEY, '')
                         if settings.contains(persistence.LEGACY_TARGET_KEY)
                         else None)
        cards = persistence.build_migrated_cards(legacy_cards, legacy_source,
                                                 legacy_target)
        self._write_cards(settings, cards)
        for key in (persistence.LEGACY_CARDS_KEY, persistence.LEGACY_SOURCE_KEY,
                    persistence.LEGACY_TARGET_KEY):
            if settings.contains(key):
                settings.remove(key)
        self._logger.info('Migrated legacy settings to v%d',
                          persistence.SETTINGS_VERSION)
        return cards

    def _on_copy_button(self):
        """Single Start/Cancel handler; branches on the running state."""
        if self._running:
            self._on_queue_cancel()
        else:
            self._on_queue_start()

    def _on_queue_start(self):
        self.console_info('----- Starting queue -----')
        self._cards_widget.set_enabled(False)
        self._shutdown_opt.setEnabled(False)

        self._running = True
        self._copy_btn.setText('Cancel')
        self._queue_canceled = False

        # run the prescript
        settings = QSettings()
        prescript = QFileInfo(settings.value('prescript', '-', type=str))
        if prescript.fileName() == '-':
            self._on_queue_setup()
            return

        if prescript.isExecutable():
            self.console_info(f'Running prescript: {prescript.fileName()}')
            self._prescript.setProgram(prescript.filePath())
            self._prescript.start()
        else:
            self.console_error(
                f'Prescript not executable: {prescript.fileName()}')
            # Not user-initiated, but the run cannot proceed; mark canceled so
            # we don't trigger shutdown-on-complete, and reset the UI.
            self._queue = []
            self._queue_canceled = True
            self._on_queue_stop()

    def _on_queue_setup(self):
        self._queue = []
        for c in self._cards_widget.cards():
            c.update_progress(100, 0, '-')
            self._queue.append(c)
        self.advance_queue.emit()

    def _on_advance_queue(self):
        if len(self._queue) == 0:
            self._on_queue_stop()
            return

        self._current_copy = self._queue.pop(0)
        src = self._current_copy.source_path
        dest = self._current_copy.target_path
        job_id = self._current_copy.list_index
        if len(src) == 0:
            self._on_copy_failed(
                f'Error: Queue item #{job_id} missing source directory')
        elif len(dest) == 0:
            self._on_copy_failed(
                f'Error: Queue item #{job_id} missing destination directory')

        # Run the job
        else:
            self.console_info(f'Copying: \'{src}\' -> \'{dest}\'')
            args = rclone.default_args()
            args.extend(['copy', src, dest])
            self._rclone.setArguments(args)
            self._copy_start = dt.datetime.now(tz=dt.timezone.utc)
            self._rclone.start()

    def _on_queue_cancel(self):
        self.console_warning('Canceling transfers...')
        self._queue = []
        self._queue_canceled = True
        self._stop_processes()

    def _on_queue_stop(self):
        self.console_info('--------------------------')
        self._cards_widget.set_enabled(True)
        self._shutdown_opt.setEnabled(True)
        self._running = False
        self._copy_btn.setText('Start')

        self._current_copy = None
        if self._shutdown_opt.isChecked() and not self._queue_canceled:
            self._on_request_shutdown()

    def _on_prescript_exit(self, exit_code, exit_status):
        # Always print output
        logger = logging.getLogger('CopyTool')
        out = str(self._prescript.readAllStandardOutput(), 'utf-8').strip()
        if out:
            logger.debug(f'Prescript (STDOUT):\n{out}')
        out = str(self._prescript.readAllStandardError(), 'utf-8').strip()
        if out:
            logger.debug(f'Prescript (STDERR):\n{out}')
        if self._queue_canceled:
            self._on_copy_canceled('Transfers canceled')
        elif exit_status == QProcess.CrashExit or exit_code != 0:
            self._on_copy_failed('Prescript failed')
        else:
            self._on_queue_setup()

    def _on_copy_complete(self):
        if self._current_copy is not None:
            duration = dt.datetime.now(tz=dt.timezone.utc) - self._copy_start
            self.console_info(f'Copy complete (Elapsed: {duration})')
            self._current_copy.update_progress(1, 1, 'Done')
        self.advance_queue.emit()

    def _on_copy_failed(self, msg: str):
        self.console_error(msg)
        if self._current_copy is not None:
            self._current_copy.update_progress(100, 0,
                                               '<font color="Red">Error</font>')
        self.advance_queue.emit()

    def _on_copy_canceled(self, msg: str):
        self.console_warning(msg)
        if self._current_copy is not None:
            self._current_copy.update_progress(100, 0,
                                               '<font color="#d47500">Canceled'
                                               '</font>')
        self.advance_queue.emit()

    def _on_copy_process_exit(self, exit_code: int,
                              exit_status: QProcess.ExitStatus):
        if self._queue_canceled:
            self._on_copy_canceled('Transfers canceled')
        elif exit_status == QProcess.CrashExit:
            self._on_copy_failed(self._rclone.errorString())
        else:
            # 0 -> complete, 9 -> complete (warning), 1-8/unexpected -> failure.
            verdict = rclone.classify_exit_code(exit_code)
            if verdict == 'complete':
                self._on_copy_complete()
            elif verdict == 'warning':
                self.console_warning(
                    f'Warning: {rclone.exit_code_string(exit_code)}')
                self._on_copy_complete()
            else:
                self._on_copy_failed(
                    f'Error: {rclone.exit_code_string(exit_code)}')

    def _on_stderr_ready(self):
        lines = str(self._rclone.readAllStandardError(), 'utf-8').splitlines()
        for line in lines:
            self._process_stderr_line(line)

    def _process_stderr_line(self, line):
        logger = logging.getLogger('CopyTool')
        status = rclone.parse_log_message(line)
        if status is None:
            logger.debug(f'[STDERR] {line}')
            return

        if status['type'] == 'PROGRESS':
            # A late/buffered progress line can arrive after the job finished.
            if self._current_copy is None:
                return

            # Convert total and sent for bitmath
            try:
                total = bitmath.parse_string(
                    f'{status["total"]} {status["total_unit"]}').best_prefix()
                sent = bitmath.parse_string(
                    f'{status["sent"]} {status["sent_unit"]}')

                # Convert to ints for progress bar
                sent = int(math.floor(total.from_other(sent).value))
                total = int(math.floor(total.value))
            except (ValueError, TypeError):
                logger.debug(f'[STDERR] unparsable progress: {line}')
                return

            # Report transfer progress to debug log
            xfr = ''
            if status['files'] is not None:
                xfr = f' (xfr {status["files"]}/{status["files_total"]})'
            eta = f'{status["eta"]}, {status["rate"]} {status["rate_unit"]}'
            logger.debug(f'{eta}{xfr}')

            # Update the progress bar
            self._current_copy.update_progress(total, sent, eta)

        elif status['loglevel'] == 'DEBUG':
            logger.debug(status['message'])
        elif status['loglevel'] == 'INFO':
            logger.info(status['message'])
        elif status['loglevel'] == 'NOTICE':
            logger.warning(status['message'])
        elif status['loglevel'] == 'ERROR':
            self.console_error(status['message'])

    def _on_stdout_ready(self):
        logger = logging.getLogger('CopyTool')
        lines = str(self._rclone.readAllStandardOutput(), 'utf-8').splitlines()
        for line in lines:
            logger.debug(f'[STDOUT] {line}')

    def _on_request_shutdown(self):
        logger = logging.getLogger('CopyTool')
        if sys.platform == 'win32':
            logger.info('Requesting system shutdown')
            cmd = 'shutdown /s /t 30 /d p:0:0 /c "CopyTool transfer completed."'
            subprocess.run(cmd)
            QCoreApplication.quit()
        else:
            logger.warning('Shutdown requests not support on this platform')

    def console_info(self, m: str):
        self._logger.info(m)
        self._console.append(f'<font color="Gray">{m}</font>')

    def console_warning(self, m: str):
        self._logger.warning(m)
        self._console.append(f'<font color="#d47500">{m}</font>')

    def console_error(self, m: str):
        self._logger.error(m)
        self._console.append(f'<font color="Red">{m}</font>')

    def console_complete(self, m: str):
        self._logger.info(m)
        self._console.append(f'<font color="limegreen">{m}</font>')


class SettingsWindow(QDialog):
    def __init__(self, parent=None):
        super(SettingsWindow, self).__init__(parent)
        self.setModal(True)
        self.setWindowTitle('CopyTool')
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        # rclone settings
        rclone_group = QGroupBox()
        rclone_group.setTitle('Preferences')
        rclone_layout = QGridLayout()
        rclone_group.setLayout(rclone_layout)
        main_layout.addWidget(rclone_group)

        self._stats_time = QLineEdit()
        self._stats_time.setText(rclone.default_stats_time())
        self._stats_time.setToolTip('<p>Progress reporting interval in '
                                    'rclone\'s duration format (e.g. 500ms, '
                                    '1s, 5m). Shorter intervals will update '
                                    'the progress bar more frequently, but '
                                    'could decrease UI performance.</p>')
        rclone_layout.addWidget(QLabel('Stats Time:'), 0, 0, Qt.AlignLeft)
        rclone_layout.addWidget(self._stats_time, 0, 1, Qt.AlignLeft)

        self._backlog = QSpinBox()
        self._backlog.setMinimum(-1)
        self._backlog.setMaximum(2 ** 31 - 1)
        self._backlog.setValue(rclone.default_max_backlog())
        self._backlog.setToolTip('<p>Maximum size of the rclone transfer '
                                 'backlog (the list of files remaining to be '
                                 'transferred). Larger values will result in '
                                 'more accurate ETA estimates at the expense '
                                 'of more RAM usage (~1KiB per file). Set to '
                                 '-1 to make the backlog as large as '
                                 'possible.</p>')
        rclone_layout.addWidget(QLabel('Max. Backlog:'), 1, 0, Qt.AlignLeft)
        rclone_layout.addWidget(self._backlog, 1, 1, Qt.AlignLeft)

        self._pre_script = QLabel('-')
        self._pre_script.setToolTip(self._pre_script.text())
        self._pre_button = QPushButton('...')
        self._pre_clear = QPushButton('Clear')
        rclone_layout.addWidget(QLabel('Prescript:'), 2, 0, Qt.AlignLeft)
        rclone_layout.addWidget(self._pre_script, 2, 1, Qt.AlignLeft)
        rclone_layout.addWidget(self._pre_button, 2, 2, Qt.AlignCenter)
        rclone_layout.addWidget(self._pre_clear, 2, 3, Qt.AlignCenter)
        self._pre_button.clicked.connect(self._on_select_prescript)
        self._pre_clear.clicked.connect(self._on_clear_prescript)

        self._file_picker = QFileDialog()
        self._file_picker.setFileMode(QFileDialog.ExistingFile)
        self._file_picker.setDirectory(
            QStandardPaths.writableLocation(QStandardPaths.HomeLocation))

        # Button box
        button_box = QDialogButtonBox(QDialogButtonBox.Save
                                      | QDialogButtonBox.Cancel | QDialogButtonBox.RestoreDefaults)
        main_layout.addWidget(button_box)
        button_box.accepted.connect(self._close_and_save)
        button_box.rejected.connect(self._close_and_reset)
        button_box.button(QDialogButtonBox.RestoreDefaults).clicked.connect(
            self._restore_defaults)

        # Limit size to current widgets
        self.setFixedSize(self.sizeHint())

        # Load settings
        self._load_settings()

    def closeEvent(self, event: QCloseEvent):
        self._close_and_reset()
        event.accept()

    def _close_and_save(self):
        self._save_settings()
        self.accept()

    def _close_and_reset(self):
        self._load_settings()
        self.reject()

    def _save_settings(self):
        settings = QSettings()

        rclone.set_stats_time(self._stats_time.text())
        settings.setValue('rclone/stats', self._stats_time.text())

        rclone.set_max_backlog(self._backlog.value())
        settings.setValue('rclone/max_backlog', self._backlog.value())

        settings.setValue('prescript', self._pre_script.text())

    def _load_settings(self):
        settings = QSettings()

        stats_time = settings.value('rclone/stats',
                                    rclone.default_stats_time(),
                                    type=str)
        self._stats_time.setText(stats_time)
        rclone.set_stats_time(stats_time)

        backlog = settings.value('rclone/max_backlog',
                                 rclone.default_max_backlog(),
                                 type=int)
        self._backlog.setValue(backlog)
        rclone.set_max_backlog(backlog)

        prescript = settings.value('prescript', '-', type=str)
        self._pre_script.setText(prescript)
        self._pre_script.setToolTip(self._pre_script.text())
        if prescript != '-':
            self._file_picker.setDirectory(prescript)

    def _restore_defaults(self):
        self._stats_time.setText(rclone.default_stats_time())
        self._backlog.setValue(rclone.default_max_backlog())
        self._pre_script.setText('-')
        self._pre_script.setToolTip(self._pre_script.text())

    def _on_select_prescript(self):
        self._file_picker.setFileMode(QFileDialog.ExistingFile)
        if not self._file_picker.exec():
            return

        file = self._file_picker.selectedFiles()[0]
        self._pre_script.setText(file)
        self._pre_script.setToolTip(self._pre_script.text())

    def _on_clear_prescript(self):
        self._pre_script.setText('-')
        self._pre_script.setToolTip(self._pre_script.text())


#: The live MainWindow, used by the crash/exit handlers to stop child
#: processes. Set once the window is constructed.
_active_window = None


def _terminate_active_processes():
    """Best-effort termination of any running child processes. Safe to call
    during interpreter shutdown / from a crash handler."""
    if _active_window is not None:
        try:
            _active_window._stop_processes()
        except Exception:
            pass


def _excepthook(exc_type, exc, tb):
    """Log unhandled exceptions and stop child processes before exiting so a
    crash never orphans a running rclone/prescript."""
    logging.getLogger('CopyTool').critical(
        'Unhandled exception', exc_info=(exc_type, exc, tb))
    _terminate_active_processes()
    sys.__excepthook__(exc_type, exc, tb)


def main():
    global _active_window

    app = QApplication(sys.argv)
    QCoreApplication.setOrganizationName('EduceLab')
    QCoreApplication.setApplicationName('CopyTool')
    QCoreApplication.setApplicationVersion(__version__)

    setup_logging(log_level=logging.DEBUG)
    logger = logging.getLogger('CopyTool')
    logger.info(
        f'Launching {QCoreApplication.organizationName()} '
        f'{QCoreApplication.applicationName()} '
        f'v{QCoreApplication.applicationVersion()}')

    # Stop child processes on unhandled exceptions and on any interpreter exit.
    sys.excepthook = _excepthook
    atexit.register(_terminate_active_processes)

    app_icon = QIcon(app_icon_path())
    app.setWindowIcon(app_icon)

    main_window = MainWindow()
    _active_window = main_window
    main_window.setWindowTitle('CopyTool')
    main_window.setWindowIcon(app_icon)
    main_window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
