from PySide6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QTextEdit
from datetime import datetime

APP_NAME = "Терминал"
APP_ICON = "terminal"
APP_VERSION = "0.3"
APP_AUTHOR = "MountOS"


def _get_vfs(widget):
    p = widget
    while p is not None:
        if hasattr(p, "vfs"):
            return p.vfs
        p = p.parent()
    return None


def build():
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(16, 12, 16, 16)
    lay.setSpacing(10)

    out = QTextEdit()
    out.setReadOnly(True)
    out.setText("MountOS Shell v0.3\nВведите 'help' для списка команд.\n\n")
    out.setStyleSheet("""
        QTextEdit {
            background: rgba(0,0,0,0.30);
            color: #B9F6CA;
            border: 1px solid rgba(255,255,255,0.10);
            border-radius: 12px;
            padding: 10px;
            font-family: 'Consolas', monospace;
            font-size: 13px;
        }
    """)
    lay.addWidget(out)

    inp = QLineEdit()
    inp.setPlaceholderText("/ $")
    inp.setStyleSheet("""
        QLineEdit {
            background: rgba(255,255,255,0.08);
            color: white;
            border: 1px solid rgba(255,255,255,0.15);
            border-radius: 10px;
            padding: 8px 12px;
            font-family: 'Consolas', monospace;
            font-size: 13px;
        }
        QLineEdit:focus { border: 1px solid rgba(110,198,255,0.6); }
    """)
    lay.addWidget(inp)

    ctx = {"cwd": "/"}

    def prompt():
        inp.setPlaceholderText(f"{ctx['cwd']} $")

    def run():
        vfs = _get_vfs(w)
        raw = inp.text().strip()
        if not raw:
            return
        out.append(f"{ctx['cwd']} $ {raw}")

        parts = raw.split()
        cmd = parts[0]
        args = parts[1:]

        if cmd == "help":
            out.append("Доступно: help, pwd, cd <path>, ls [path], mkdir <path>,")
            out.append("          touch <file>, cat <file>, rm <path>,")
            out.append("          echo <text> > <file>, date, clear, whoami, uname")
        elif cmd == "pwd":
            out.append(ctx["cwd"])
        elif cmd == "cd":
            if not args:
                ctx["cwd"] = "/"
            else:
                target = _resolve(vfs, ctx["cwd"], args[0])
                if vfs.is_dir(target):
                    ctx["cwd"] = target
                else:
                    out.append(f"cd: нет такого каталога: {args[0]}")
        elif cmd == "ls":
            path = _resolve(vfs, ctx["cwd"], args[0]) if args else ctx["cwd"]
            for it in vfs.listdir(path):
                mark = "/" if it["is_dir"] else ""
                out.append("  " + it["name"] + mark)
        elif cmd == "mkdir":
            if args:
                vfs.mkdir(_resolve(vfs, ctx["cwd"], args[0]))
        elif cmd == "touch":
            if args:
                vfs.write_text(_resolve(vfs, ctx["cwd"], args[0]), "")
        elif cmd == "cat":
            if args:
                out.append(vfs.read_text(_resolve(vfs, ctx["cwd"], args[0]), "[нет файла]"))
        elif cmd == "rm":
            if args:
                vfs.delete(_resolve(vfs, ctx["cwd"], args[0]))
        elif cmd == "echo":
            text = raw[5:]
            if ">" in text:
                body, _, fname = text.partition(">")
                vfs.write_text(_resolve(vfs, ctx["cwd"], fname.strip()),
                               body.strip() + "\n")
            else:
                out.append(text)
        elif cmd == "date":
            out.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        elif cmd == "clear":
            out.clear()
        elif cmd == "whoami":
            out.append("mount-user")
        elif cmd == "uname":
            out.append("MountOS 0.3 (Liquid Glass Edition)")
        else:
            out.append(f"mountos: команда не найдена: {cmd}")

        inp.clear()
        prompt()

    inp.returnPressed.connect(run)
    prompt()
    return w


def _resolve(vfs, cwd, path):
    if not vfs:
        return path
    if path.startswith("/"):
        return path
    return vfs.join(cwd, path)