import sys

from PySide6.QtCore import (Qt, Signal)
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (QApplication, QFileDialog, QFrame, QGroupBox,
                               QHBoxLayout, QLabel, QLayout, QLineEdit,
                               QMainWindow, QProgressBar, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)


class CopyJobCard(QFrame):
    clickedClose = Signal(object)

    _list_index = None

    def __init__(self, parent=None):
        super(CopyJobCard, self).__init__(parent)
        self.setLayout(QVBoxLayout())
        self.setBackgroundRole(QPalette.Window)
        self.setAutoFillBackground(True)
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setMinimumSize(600, 150)
        self.setMaximumHeight(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.layout().setSpacing(0)

        title_widget = QWidget()
        title_layout = QHBoxLayout()
        title_widget.setLayout(title_layout)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(0)
        self.layout().addWidget(title_widget)

        self._list_index = None
        self._card_label = QLabel()
        self._card_label.setForegroundRole(QPalette.PlaceholderText)
        self._card_label.setStyleSheet('QLabel{font-size: 10pt}')
        title_layout.addSpacing(2)
        title_layout.addWidget(self._card_label, 0, Qt.AlignLeft)

        close_button = QPushButton('\u00d7')
        close_button.setForegroundRole(QPalette.PlaceholderText)
        close_button.setFlat(True)
        close_button.setLayout(QHBoxLayout())
        close_button.layout().setContentsMargins(0, 0, 0, 0)
        close_button.layout().setSpacing(0)
        close_button.layout().setAlignment(Qt.AlignCenter)
        close_button.setMinimumSize(24, 24)
        close_button.setMaximumSize(24, 24)
        close_button.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Maximum)
        close_button.setStyleSheet("""
            QPushButton {
                color: palette(dark);
            }
            QPushButton:hover {
                color: palette(text);
            }
            QPushButton:pressed {
                color: palette(text);
                border: none;
                background-color: palette(dark);
            }
            """)
        close_button.setToolTip('Remove')
        close_button.clicked.connect(self._on_click_close)
        self._close_button = close_button
        title_layout.addWidget(close_button, 0, Qt.AlignRight)

        self._src_tgt_widgets = QWidget()
        src_tgt_layout = QHBoxLayout()
        src_tgt_layout.setContentsMargins(0, 0, 0, 0)
        self._src_tgt_widgets.setLayout(src_tgt_layout)
        self.layout().addWidget(self._src_tgt_widgets)

        lhs = QGroupBox('Source')
        lhs.setLayout(QHBoxLayout())
        src_tgt_layout.addWidget(lhs)

        self._src_dir = QLineEdit()
        lhs.layout().addWidget(self._src_dir)

        select_src_dir = QPushButton('...')
        select_src_dir.clicked.connect(self._on_select_src)
        lhs.layout().addWidget(select_src_dir)

        rhs = QGroupBox('Target')
        rhs.setLayout(QHBoxLayout())
        src_tgt_layout.addWidget(rhs)

        self._tgt_dir = QLineEdit()
        rhs.layout().addWidget(self._tgt_dir)

        select_tgt_dir = QPushButton('...')
        select_tgt_dir.clicked.connect(self._on_select_tgt)
        rhs.layout().addWidget(select_tgt_dir)

        self.layout().addSpacing(10)

        # Progress bar
        prog_widget = QWidget()
        prog_widget.setLayout(QHBoxLayout())
        prog_widget.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().addWidget(prog_widget)
        self._progress = QProgressBar()
        self._progress.setRange(0, 100)
        prog_widget.layout().addWidget(self._progress)
        self._eta_label = QLabel(text='eta: -')
        prog_widget.layout().addWidget(self._eta_label)

        self._dir_picker = QFileDialog()
        self._dir_picker.setFileMode(QFileDialog.Directory)

    def set_enabled(self, b: bool):
        self._src_tgt_widgets.setEnabled(b)
        self._close_button.setEnabled(b)

    def _on_select_src(self):
        self._dir_picker.setDirectory(self._src_dir.text())
        if self._dir_picker.exec():
            directory = self._dir_picker.selectedFiles()[0]
            self._src_dir.setText(directory)

    def _on_select_tgt(self):
        self._dir_picker.setDirectory(self._tgt_dir.text())
        if self._dir_picker.exec():
            directory = self._dir_picker.selectedFiles()[0]
            self._tgt_dir.setText(directory)

    def update_progress(self, total: int, sent: int, eta: str):
        self._progress.setMaximum(total)
        self._progress.setValue(sent)
        self._eta_label.setText(f'eta: {eta}')

    def _on_click_close(self):
        self.clickedClose.emit(self)

    @property
    def list_index(self) -> int:
        return self._list_index

    @list_index.setter
    def list_index(self, index: int):
        self._list_index = index
        self._card_label.setText(str(index))

    @property
    def source_path(self) -> str:
        return self._src_dir.text()

    @source_path.setter
    def source_path(self, p: str):
        self._src_dir.setText(p)

    @property
    def target_path(self) -> str:
        return self._tgt_dir.text()

    @target_path.setter
    def target_path(self, p: str):
        self._tgt_dir.setText(p)

    @property
    def settings(self):
        return self.source_path, self.target_path

    @settings.setter
    def settings(self, src_tgt):
        self.source_path, self.target_path = src_tgt


class AddCard(QPushButton):
    def __init__(self, parent=None):
        super(AddCard, self).__init__(parent)
        self.setLayout(QVBoxLayout())
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setAlignment(Qt.AlignCenter)
        self.setMinimumSize(100, 40)
        self.setMaximumHeight(40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.setToolTip('Add')

        self.setText('+')
        self.setForegroundRole(QPalette.PlaceholderText)
        self.setStyleSheet("""
            QPushButton {
                color: palette(window);
                border-width: 2px;
                border-style: dashed;
                border-color: palette(window);
                border-radius: 4px;
            }
            QPushButton:hover {
                color: palette(dark);
                border-color: palette(dark);
                background-color: palette(window);
            }
            QPushButton:pressed {
                color: palette(window-text);
                border-style: none;
                background-color: palette(dark);
            }
            """)

    @property
    def list_index(self) -> int:
        return -1

    @list_index.setter
    def list_index(self, index: int):
        pass


class CardListWidget(QScrollArea):
    _cards_holder = None
    _cards = None

    def __init__(self, parent=None):
        super(CardListWidget, self).__init__(parent=parent)

        self.setBackgroundRole(QPalette.Base)
        self.setFrameStyle(QFrame.StyledPanel | QFrame.Sunken)
        self.setWidgetResizable(True)
        self.setSizePolicy(QSizePolicy.MinimumExpanding,
                           QSizePolicy.MinimumExpanding)
        self.setMinimumSize(650, 150)

        self._cards_holder = QWidget()
        self._cards_holder.setLayout(QVBoxLayout())
        self._cards_holder.layout().setSizeConstraint(QLayout.SetMinAndMaxSize)
        self._cards_holder.setSizePolicy(QSizePolicy.MinimumExpanding,
                                         QSizePolicy.MinimumExpanding)
        self._cards_holder.setMinimumSize(600, 100)
        self._add_card = AddCard()
        self._add_card.clicked.connect(self._on_new_card)
        self._cards_holder.layout().addWidget(self._add_card)
        self.setWidget(self._cards_holder)

        self._cards = []

    def _on_new_card(self):
        self.add_card(CopyJobCard())

    def add_card(self, card: QWidget):
        # Insert before the trailing AddCard button (always the last item).
        insert_at = max(self._cards_holder.layout().count() - 1, 0)
        self._cards_holder.layout().insertWidget(insert_at, card)
        self._cards.append(card)
        card.clickedClose.connect(self.remove_card)
        self._renumber()
        self._update_height()

    def remove_card(self, card: QWidget):
        # Identity-based removal so a stale/duplicate index can never pop the
        # wrong card. Removing the last card is allowed (empty is a valid
        # state now that cards persist as JSON).
        if card not in self._cards:
            return
        self._cards.remove(card)
        card.clickedClose.disconnect(self.remove_card)
        card.setParent(None)
        self._cards_holder.layout().removeWidget(card)
        self._renumber()
        self._update_height()

    def _renumber(self):
        for idx, card in enumerate(self._cards):
            card.list_index = idx + 1

    def _update_height(self):
        self.setMaximumHeight(max(self._cards_holder.sizeHint().height(),
                                  self.sizeHint().height()))

    def cards(self):
        return self._cards

    def set_enabled(self, b: bool):
        self._add_card.setEnabled(b)
        for c in self._cards:
            c.set_enabled(b)

    @property
    def card_list(self):
        return [c.settings for c in self._cards]

    @card_list.setter
    def card_list(self, cards):
        # Replace any existing cards (assignment semantics, not append).
        for existing in list(self._cards):
            self.remove_card(existing)
        for c in (cards or []):
            try:
                src, tgt = c
            except (TypeError, ValueError):
                # Skip malformed entries rather than crash on load.
                continue
            card = CopyJobCard()
            card.settings = (src, tgt)
            self.add_card(card)


def main():
    app = QApplication(sys.argv)
    window = QMainWindow()
    card_list = CardListWidget()
    window.setCentralWidget(card_list)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
