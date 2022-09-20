import datetime as dt
import logging
import math
import os
import sys
import time
from functools import partialmethod
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Dict, Tuple

import bitmath
from PySide6.QtCore import (QCoreApplication, QObject, QSettings,
                            QStandardPaths, QThread, Qt, Signal)
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (QApplication, QFileDialog, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMainWindow,
                               QMessageBox, QProgressBar, QPushButton,
                               QTextEdit, QVBoxLayout, QWidget)

import rclone


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
    cnt = 0
    size = 0
    for p in d.rglob('*'):
        if p.is_file():
            cnt += 1
            size += p.stat().st_size
    return size, cnt


class RcloneController(QObject):
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
            rclone.copy(src, dest, listener=self._on_status_update)
        except FileNotFoundError as e:
            logger.error(e)
            self.copy_failed.emit(f'Copy failed. rclone failed to launch.')
            return
        duration = dt.datetime.now(tz=dt.timezone.utc) - start
        self.copy_complete.emit(str(duration))

    def on_status_update(self, status: Dict):
        sent = bitmath.parse_string(f'{status["sent"]} {status["sent_unit"]}')
        total = bitmath.parse_string(
            f'{status["total"]} {status["total_unit"]}')
        sent = int(math.floor(sent.to_Kib().value))
        total = int(math.floor(total.to_Kib().value))
        eta = f'{status["eta"]}, {status["rate"]} {status["rate_unit"]}'
        self.progress_update.emit(total, sent, eta)

    _on_status_update = partialmethod(on_status_update)


class MainWindow(QMainWindow):
    _src_dir = None
    _src_label = None
    _tgt_dir = None
    _dir_picker = None
    _rclone = None
    _rclone_thread = None
    _start_time = None
    _logger = None

    submit_copy = Signal(str, str)

    def __init__(self, parent=None):
        super(MainWindow, self).__init__(parent=parent)

        self._logger = logging.getLogger('CopyTool')

        if not rclone.is_installed():
            self._logger.error('rclone not detected')
            self._logger.info(QApplication.applicationDirPath())
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

        # Two columns
        self._columns_widget = QWidget()
        columns_layout = QHBoxLayout()
        self._columns_widget.setLayout(columns_layout)
        columns_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self._columns_widget)

        # LHS
        lhs = QGroupBox('Source')
        lhs.setLayout(QVBoxLayout())
        lhs.layout().setAlignment(Qt.AlignTop)
        columns_layout.addWidget(lhs)

        dir_widgets = QWidget()
        dir_widgets.setLayout(QHBoxLayout())
        dir_widgets.layout().setContentsMargins(0, 0, 0, 0)
        lhs.layout().addWidget(dir_widgets)
        self._src_dir = QLineEdit()
        self._src_dir.textChanged.connect(self._on_change_src_dir)
        dir_widgets.layout().layout().addWidget(self._src_dir)

        select_src_dir = QPushButton('...')
        select_src_dir.clicked.connect(self._on_select_src)
        dir_widgets.layout().layout().addWidget(select_src_dir)

        self._src_label = QLabel()
        self._src_label.setContentsMargins(0, 0, 0, 0)
        lhs.layout().addWidget(self._src_label)

        # RHS
        rhs = QGroupBox('Target')
        rhs.setLayout(QVBoxLayout())
        rhs.layout().setAlignment(Qt.AlignTop)
        columns_layout.addWidget(rhs)

        dir_widgets = QWidget()
        dir_widgets.setLayout(QHBoxLayout())
        dir_widgets.layout().setContentsMargins(0, 0, 0, 0)
        rhs.layout().addWidget(dir_widgets)

        self._tgt_dir = QLineEdit()
        dir_widgets.layout().addWidget(self._tgt_dir)

        select_tgt_dir = QPushButton('...')
        select_tgt_dir.clicked.connect(self._on_select_tgt)
        dir_widgets.layout().addWidget(select_tgt_dir)

        self._copy_btn = QPushButton('Copy')
        self._copy_btn.clicked.connect(self._on_copy_start)
        rhs.layout().addWidget(self._copy_btn)

        self._dir_picker = QFileDialog()
        self._dir_picker.setFileMode(QFileDialog.Directory)

        # Progress bar
        prog_widget = QWidget()
        prog_widget.setLayout(QHBoxLayout())
        prog_widget.layout().setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(prog_widget)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        prog_widget.layout().addWidget(self._progress)
        self._eta_label = QLabel(text='eta: -')
        prog_widget.layout().addWidget(self._eta_label)

        self._console = QTextEdit()
        self._console.setReadOnly(True)
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
        self._rclone.progress_update.connect(self._on_progress_update)
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
        settings.setValue('source', self._src_dir.text())
        settings.setValue('target', self._tgt_dir.text())

    def _load_settings(self):
        settings = QSettings()
        if settings.contains("mainWin/geometry"):
            self.restoreGeometry(settings.value("mainWin/geometry"))
        if settings.contains("mainWin/state"):
            self.restoreState(settings.value("mainWin/state"))
        self._src_dir.setText(settings.value('source', ''))
        self._tgt_dir.setText(settings.value('target', ''))

    def _on_select_src(self):
        self._dir_picker.setDirectory(self._src_dir.text())
        if self._dir_picker.exec():
            directory = self._dir_picker.selectedFiles()[0]
            self._src_dir.setText(directory)

    def _on_change_src_dir(self, d: str):
        has_path = len(d) > 0
        d = Path(d)
        can_read = os.access(d, os.R_OK)
        # TODO: Do in parallel
        if False and has_path and can_read and d.exists():
            try:
                size, files = get_dir_size(Path(d))
                self._src_label.setText(
                    f'Files: {files}, Size: {bitmath.best_prefix(size).format("{value:.2f} {unit}")}')
            except PermissionError:
                self._src_label.clear()
        else:
            self._src_label.clear()

    def _on_select_tgt(self):
        self._dir_picker.setDirectory(self._tgt_dir.text())
        if self._dir_picker.exec():
            directory = self._dir_picker.selectedFiles()[0]
            self._tgt_dir.setText(directory)

    def _on_copy_start(self):
        src = self._src_dir.text()
        dest = self._tgt_dir.text()
        if len(src) == 0:
            self.console_error(f'Error: Missing source directory')
            return
        if len(dest) == 0:
            self.console_error(f'Error: Missing destination directory')
            return
        self._columns_widget.setDisabled(True)
        self.submit_copy.emit(src, dest)

    def _on_copy_complete(self, duration: str):
        self._columns_widget.setEnabled(True)
        self.console_complete(f'Copy complete (Elapsed: {duration})')

    def _on_copy_failed(self, msg: str):
        self._columns_widget.setEnabled(True)
        self.console_error(msg)

    def _on_progress_update(self, total: int, sent: int, eta: str):
        self._progress.setMaximum(total)
        self._progress.setValue(sent)
        self._eta_label.setText(f'eta: {eta}')

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
        self._progress.setRange(0, 0)
        self._eta_label.setText(f'eta: -')


def main():
    app = QApplication(sys.argv)
    QCoreApplication.setOrganizationName('EduceLab')
    QCoreApplication.setApplicationName('CopyTool')
    QCoreApplication.setApplicationVersion("1.0.0")

    setup_logging()
    logger = logging.getLogger('CopyTool')
    logger.info(
        f'Launching {QCoreApplication.organizationName()} '
        f'{QCoreApplication.applicationName()} '
        f'v{QCoreApplication.applicationVersion()}')

    main_window = MainWindow()
    main_window.setWindowTitle('CopyTool')
    main_window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
