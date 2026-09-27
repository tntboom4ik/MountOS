from PySide6.QtWidgets import (QWidget, QVBoxLayout, QGridLayout,
                                QPushButton, QLabel)
from PySide6.QtCore import Qt

APP_NAME = "Калькулятор"
APP_ICON = "🧮"
APP_VERSION = "1.0"
APP_AUTHOR = "MountOS Team"


def build():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(20, 16, 20, 20)
    lay.setSpacing(12)

    display = QLabel("0")
    display.setAlignment(Qt.AlignRight)
    display.setStyleSheet("""
        background: rgba(0,0,0,0.25);
        color: white;
        font-size: 32px;
        font-weight: 300;
        border: 1px solid rgba(255,255,255,0.10);
        border-radius: 14px;
        padding: 16px 20px;
        letter-spacing: 2px;
    """)
    lay.addWidget(display)

    grid = QGridLayout()
    grid.setSpacing(8)

    state = {"expr": ""}

    def press(val):
        if val == "C":
            state["expr"] = ""
            display.setText("0")
        elif val == "=":
            try:
                result = str(eval(state["expr"]))
                display.setText(result)
                state["expr"] = result
            except Exception:
                display.setText("ошибка")
                state["expr"] = ""
        else:
            state["expr"] += val
            display.setText(state["expr"])

    layout = [
        ["C", "(", ")", "/"],
        ["7", "8", "9", "*"],
        ["4", "5", "6", "-"],
        ["1", "2", "3", "+"],
        ["0", ".", "=", ""],
    ]

    for r, row in enumerate(layout):
        for c, val in enumerate(row):
            if not val:
                continue
            b = QPushButton(val)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(52)
            if val == "=":
                b.setStyleSheet("""
                    QPushButton {
                        background: #6EC6FF; color: white;
                        font-size: 18px; font-weight: 600;
                        border: none; border-radius: 12px;
                    }
                    QPushButton:hover { background: #8FD5FF; }
                """)
            elif val in "/*-+":
                b.setStyleSheet("""
                    QPushButton {
                        background: rgba(110,198,255,0.20);
                        color: #A0DEFF; font-size: 18px;
                        border: 1px solid rgba(110,198,255,0.35);
                        border-radius: 12px;
                    }
                    QPushButton:hover { background: rgba(110,198,255,0.35); }
                """)
            else:
                b.setStyleSheet("""
                    QPushButton {
                        background: rgba(255,255,255,0.08);
                        color: white; font-size: 16px;
                        border: 1px solid rgba(255,255,255,0.10);
                        border-radius: 12px;
                    }
                    QPushButton:hover { background: rgba(255,255,255,0.18); }
                """)
            b.clicked.connect(lambda _, v=val: press(v))
            grid.addWidget(b, r, c)

    lay.addLayout(grid)
    return w