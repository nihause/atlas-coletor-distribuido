"""Tema desktop: azul petróleo, verde água e superfícies claras."""
STYLE = """
QWidget#surface { background: #ffffff; }
QMainWindow { background: #edf2f5; }
QWidget { color: #183247; font-family: 'Ubuntu', 'Noto Sans', sans-serif; font-size: 14px; }
QLabel#title { font-size: 24px; font-weight: 700; }
QLabel#subtitle { color: #536a7d; }
QLabel#message { background: #e0efee; color: #174c47; border-radius: 8px; padding: 9px; }
QTabWidget::pane { border: 1px solid #d2dfe7; background: #ffffff; border-radius: 8px; }
QTabBar::tab { padding: 10px 22px; background: #e2eaf0; }
QTabBar::tab:selected { background: #ffffff; border-top: 3px solid #147f7a; }
QGroupBox { border: 1px solid #d2dfe7; border-radius: 8px; margin-top: 12px; padding: 7px; font-weight: 600; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QLineEdit, QSpinBox, QComboBox { background: #ffffff; border: 1px solid #a8bdcc; border-radius: 5px; padding: 8px; min-height: 20px; }
QPushButton { background: #eaf0f4; border: 1px solid #b5c7d3; border-radius: 6px; padding: 10px 16px; font-weight: 600; }
QPushButton:hover { background: #d9e8ee; }
QPushButton:disabled { color: #728695; background: #eef1f3; }
QPushButton#primary { background: #147f7a; border-color: #147f7a; color: #ffffff; }
QPushButton#primary:hover { background: #116a66; }
QLabel#metric { font-size: 24px; font-weight: 700; }
QTableWidget { border: 1px solid #d2dfe7; gridline-color: #e1e9ee; background: #ffffff; alternate-background-color: #f3f7fa; }
QHeaderView::section { background: #eaf0f4; padding: 8px; border: 0; font-weight: 600; }
QPlainTextEdit { background: #f3f7fa; border: 1px solid #d2dfe7; }
"""
