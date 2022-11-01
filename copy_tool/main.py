import datetime as dt
import logging
import math
import subprocess
import sys
import time
from functools import partialmethod
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Tuple

import bitmath
from PySide6.QtCore import (QCoreApplication, QObject, QSettings,
                            QStandardPaths, QThread, Qt, Signal)
from PySide6.QtGui import QCloseEvent, QIcon
from PySide6.QtWidgets import (QApplication, QCheckBox, QHBoxLayout,
                               QMainWindow, QMessageBox, QPushButton, QTextEdit,
                               QVBoxLayout, QWidget)

import rclone
import widgets


class ApplicationLogFilter(logging.Filter):
    allowed_names = ['CopyTool']

    def filter(self, record):
        for a in self.allowed_names:
            if a in record.name:
                return True
            else:
                return False


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


def get_dir_size(d: Path) -> Tuple[int, int]:
    """Recursively get the size and number of files in a directory."""
    cnt = 0
    size = 0
    for p in d.rglob('*'):
        if p.is_file():
            cnt += 1
            size += p.stat().st_size
    return size, cnt


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


class RcloneController(QObject):
    """Controller for managing a rclone subprocess in its own thread."""
    copy_complete = Signal(str)
    copy_failed = Signal(str)

    progress_update = Signal(int, int, str)
    message_info = Signal(str)
    message_warning = Signal(str)
    message_error = Signal(str)

    def __init__(self, parent=None):
        super(RcloneController, self).__init__(parent=parent)

    def on_submit_copy(self, src: str, dest: str):
        logger = logging.getLogger('CopyTool')
        self.message_info.emit(f'Copying: \'{src}\' -> \'{dest}\'')

        start = dt.datetime.now(tz=dt.timezone.utc)
        try:
            ret = rclone.copy(src, dest, listener=self._on_status_update)
        except FileNotFoundError as e:
            logger.error(e)
            self.copy_failed.emit(f'Copy failed. rclone failed to launch.')
            return
        if ret != 0:
            self.copy_failed.emit(f'Copy failed with return code {ret}')
        else:
            duration = dt.datetime.now(tz=dt.timezone.utc) - start
            self.copy_complete.emit(str(duration))

    def on_status_update(self, status: Dict):
        logger = logging.getLogger('CopyTool')
        if status['type'] == 'PROGRESS':
            sent = bitmath.parse_string(
                f'{status["sent"]} {status["sent_unit"]}')
            total = bitmath.parse_string(
                f'{status["total"]} {status["total_unit"]}')
            sent = int(math.floor(sent.to_Kib().value))
            total = int(math.floor(total.to_Kib().value))
            eta = f'{status["eta"]}, {status["rate"]} {status["rate_unit"]}'
            self.progress_update.emit(total, sent, eta)
        elif status['loglevel'] == 'DEBUG':
            logger.debug(status['message'])
        elif status['loglevel'] == 'INFO':
            logger.info(status['message'])
        elif status['loglevel'] == 'NOTICE':
            logger.warning(status['message'])
        elif status['loglevel'] == 'ERROR':
            self.message_error.emit(status['message'])

    _on_status_update = partialmethod(on_status_update)


class MainWindow(QMainWindow):
    _rclone = None
    _rclone_thread = None
    _start_time = None
    _logger = None
    _connection = None

    submit_copy = Signal(str, str)

    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent=parent)

        self._logger = logging.getLogger('CopyTool')

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

        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # Cards list
        self._cards_widget = widgets.CardListWidget()
        main_layout.addWidget(self._cards_widget, stretch=2)

        copy_ctrls = QWidget()
        copy_ctrls.setLayout(QHBoxLayout())
        copy_ctrls.layout().setContentsMargins(5, 0, 5, 0)
        copy_ctrls.layout().setSpacing(5)
        copy_ctrls.layout().setAlignment(Qt.AlignRight)
        main_layout.addWidget(copy_ctrls)

        self._shutdown_opt = QCheckBox('Shutdown on complete')
        self._shutdown_opt.setChecked(False)
        # Shutdown requires elevated privileges on Unix-like systems,
        # So only add option on Windows for now
        if sys.platform == 'win32':
            copy_ctrls.layout().addWidget(self._shutdown_opt)
            copy_ctrls.layout().addSpacing(25)

        self._copy_btn = QPushButton('Start')
        self._copy_btn.clicked.connect(self._on_queue_start)
        copy_ctrls.layout().addWidget(self._copy_btn, stretch=1)

        self._console = QTextEdit()
        self._console.setReadOnly(True)
        self._console.setMinimumHeight(100)
        app_str = f'{QApplication.organizationName()} ' \
                  f'{QApplication.applicationName()} ' \
                  f'v{QApplication.applicationVersion()}'
        self._console.append(f'<font color="Gray">{app_str}</font>')
        main_layout.addWidget(self._console)

        self._rclone = RcloneController()
        self._rclone_thread = QThread()
        self._rclone.moveToThread(self._rclone_thread)
        self.submit_copy.connect(self._rclone.on_submit_copy)
        self._rclone.copy_complete.connect(self._on_copy_complete)
        self._rclone.copy_failed.connect(self._on_copy_failed)
        self._rclone.message_info.connect(self.console_info)
        self._rclone.message_warning.connect(self.console_warning)
        self._rclone.message_error.connect(self.console_error)
        self._rclone_thread.finished.connect(self._rclone.deleteLater)
        self._rclone_thread.start()

        self._load_settings()

    def __del__(self):
        if self._rclone_thread is not None:
            self._rclone_thread.quit()
            self._rclone_thread.wait()

    def closeEvent(self, event: QCloseEvent):
        self._save_settings()
        event.accept()

    def _save_settings(self):
        settings = QSettings()

        settings.setValue("mainWin/geometry", self.saveGeometry())
        settings.setValue("mainWin/state", self.saveState())

        settings.setValue('cards', self._cards_widget.card_list)
        if settings.contains('source'):
            settings.remove('source')
        if settings.contains('target'):
            settings.remove('target')

    def _load_settings(self):
        settings = QSettings()
        if settings.contains("mainWin/geometry"):
            self.restoreGeometry(settings.value("mainWin/geometry"))
        if settings.contains("mainWin/state"):
            self.restoreState(settings.value("mainWin/state"))

        # Migrate source and target
        if settings.contains('source') or settings.contains('target'):
            card = widgets.CopyJobCard()
            card.source_path = settings.value('source', '')
            card.target_path = settings.value('target', '')
            self._cards_widget.add_card(card)

        # Restore cards
        if settings.contains('cards'):
            self._cards_widget.card_list = settings.value('cards')

        if len(self._cards_widget.card_list) == 0:
            self._cards_widget.add_card(widgets.CopyJobCard())

    def _on_queue_start(self):
        self.console_info('----- Starting queue -----')
        self._cards_widget.set_enabled(False)
        self._queue = []
        for c in self._cards_widget.cards():
            c.update_progress(100, 0, '-')
            self._queue.append(c)
        self._submit_next_copy()

    def _submit_next_copy(self):
        if len(self._queue) == 0:
            self._on_queue_complete()
            return

        self._current_copy = self._queue.pop(0)
        src = self._current_copy.source_path
        dest = self._current_copy.target_path
        job_id = self._current_copy.list_index
        if len(src) == 0:
            self._on_copy_failed(
                f'Error: Missing source directory (ID:{job_id})')
        elif len(dest) == 0:
            self._on_copy_failed(
                f'Error: Missing destination directory (ID:{job_id})')
        else:
            self._connection = self._rclone.progress_update.connect(
                self._current_copy.update_progress)
            self.submit_copy.emit(src, dest)

    def _on_copy_complete(self, duration: str):
        self.console_info(f'Copy complete (Elapsed: {duration})')
        self._current_copy.update_progress(1, 1, 'Done')
        self._rclone.progress_update.disconnect()
        self._submit_next_copy()

    def _on_copy_failed(self, msg: str):
        self.console_error(msg)
        self._current_copy.update_progress(100, 0,
                                           '<font color="Red">Error</font>')
        if self._connection:
            self._rclone.progress_update.disconnect()
            self._connection = False
        self._submit_next_copy()

    def _on_queue_complete(self):
        self.console_info('--------------------------')
        self._cards_widget.set_enabled(True)
        self._current_copy = None
        if self._shutdown_opt.isChecked():
            self._on_request_shutdown()

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
        self._console.append(f'<font color="Yellow">{m}</font>')

    def console_error(self, m: str):
        self._logger.error(m)
        self._console.append(f'<font color="Red">{m}</font>')

    def console_complete(self, m: str):
        self._logger.info(m)
        self._console.append(f'<font color="limegreen">{m}</font>')


def main():
    app = QApplication(sys.argv)
    QCoreApplication.setOrganizationName('EduceLab')
    QCoreApplication.setApplicationName('CopyTool')
    QCoreApplication.setApplicationVersion("1.1.0")

    setup_logging()
    logger = logging.getLogger('CopyTool')
    logger.info(
        f'Launching {QCoreApplication.organizationName()} '
        f'{QCoreApplication.applicationName()} '
        f'v{QCoreApplication.applicationVersion()}')

    app_icon = QIcon(app_icon_path())
    app.setWindowIcon(app_icon)

    main_window = MainWindow()
    main_window.setWindowTitle('CopyTool')
    main_window.setWindowIcon(app_icon)
    main_window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
