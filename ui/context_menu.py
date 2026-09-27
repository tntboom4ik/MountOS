from PySide6.QtWidgets import QMenu


def make_menu(parent=None):
    m = QMenu(parent)
    m.setStyleSheet("""
        QMenu {
            background: rgba(28, 34, 54, 0.98);
            color: white;
            border: 1px solid rgba(255,255,255,0.16);
            border-radius: 12px;
            padding: 6px;
        }
        QMenu::item {
            padding: 7px 22px 7px 14px;
            border-radius: 7px;
            font-size: 12px;
            min-width: 180px;
        }
        QMenu::item:selected {
            background: rgba(110,198,255,0.35);
        }
        QMenu::separator {
            height: 1px;
            background: rgba(255,255,255,0.10);
            margin: 5px 8px;
        }
    """)
    return m