from __future__ import annotations

TRACK_COLORS: dict[str, str] = {
    "vocals": "#0b74de",
    "bass": "#22c55e",
    "guitar": "#f59e0b",
    "piano": "#8b5cf6",
    "other": "#64748b",
    "drums": "#ef4444",
    "instrumental": "#14b8a6",
}


def pitchstems_stylesheet() -> str:
    return """
    QWidget {
        color: #0f172a;
        font-size: 12px;
    }

    QMainWindow, QWidget#appShell {
        background: #f8fafc;
    }

    QFrame#sideRail {
        background: #ffffff;
        border-right: 1px solid #e2e8f0;
    }

    QPushButton#navButton {
        background: transparent;
        border: 0;
        border-left: 3px solid transparent;
        border-radius: 6px;
        color: #172033;
        font-weight: 600;
        padding: 10px 8px;
        text-align: left;
    }

    QPushButton#navButton:checked {
        background: #eef6ff;
        border-left-color: #0b74de;
        color: #0b74de;
    }

    QLabel#brandTitle {
        color: #0f172a;
        font-size: 15px;
        font-weight: 800;
    }

    QWidget#topBar, QFrame#projectStrip, QFrame#statusCard {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
    }

    QLabel#eyebrow {
        color: #64748b;
        font-size: 9px;
        font-weight: 700;
        text-transform: uppercase;
    }

    QLabel#sectionTitle {
        color: #334155;
        font-weight: 800;
    }

    QLabel#mutedText {
        color: #64748b;
    }

    QPushButton {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 5px;
        color: #172033;
        font-weight: 600;
        min-height: 26px;
        padding: 4px 12px;
    }

    QPushButton:hover {
        border-color: #93c5fd;
        background: #f8fbff;
    }

    QPushButton:disabled {
        color: #94a3b8;
        background: #f1f5f9;
    }

    QPushButton#primaryAction {
        background: #0b74de;
        border-color: #0b74de;
        color: #ffffff;
    }

    QPushButton#transportPrimary {
        background: #0b74de;
        border-color: #0b74de;
        color: #ffffff;
        min-width: 78px;
    }

    QPushButton#transportIcon {
        min-width: 32px;
        max-width: 38px;
        padding: 4px 6px;
    }

    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTextEdit, QListWidget {
        background: #ffffff;
        border: 1px solid #d8e0ea;
        border-radius: 5px;
        selection-background-color: #bfdbfe;
    }

    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox {
        min-height: 26px;
        padding: 2px 7px;
    }

    QGroupBox {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        font-weight: 700;
        margin-top: 11px;
        padding: 10px 8px 8px 8px;
    }

    QGroupBox::title {
        color: #334155;
        left: 8px;
        subcontrol-origin: margin;
    }

    QTabWidget::pane {
        border: 1px solid #e2e8f0;
        border-radius: 6px;
        background: #ffffff;
    }

    QTabBar::tab {
        background: #ffffff;
        border: 0;
        color: #64748b;
        font-weight: 600;
        min-width: 86px;
        padding: 8px 12px;
    }

    QTabBar::tab:selected {
        color: #0b74de;
        border-bottom: 2px solid #0b74de;
    }

    QScrollArea {
        background: transparent;
        border: 0;
    }

    QSlider::groove:horizontal {
        background: #dbe4ef;
        border-radius: 2px;
        height: 4px;
    }

    QSlider::sub-page:horizontal {
        background: #0b74de;
        border-radius: 2px;
    }

    QSlider::handle:horizontal {
        background: #ffffff;
        border: 1px solid #93c5fd;
        border-radius: 6px;
        height: 12px;
        margin: -5px 0;
        width: 12px;
    }

    QStatusBar {
        background: #ffffff;
        border-top: 1px solid #e2e8f0;
        color: #334155;
    }
    """
