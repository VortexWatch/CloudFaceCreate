import sys
from PyQt6.QtWidgets import QApplication
from .core.project import Project
from .ui.main_window import MainWindow


def main(argv=None):
    argv = list(sys.argv if argv is None else argv)
    app = QApplication(argv)
    app.setApplicationName("CloudFaceCreate")
    app.setStyle("Fusion")
    win = MainWindow()
    if len(argv) > 1:
        win.open_path(argv[1])
    else:
        print("[*] The UI is blank until you open a project.")
    win.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
