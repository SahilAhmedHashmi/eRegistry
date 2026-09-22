LIGHT = """
QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: #172033; background: #f5f7fb; }
QMainWindow, QDialog { background: #f5f7fb; }
QFrame#card { background: white; border: 1px solid #dfe5ef; border-radius: 10px; }
QLineEdit, QTextEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QTableWidget {
  background: white; border: 1px solid #cbd5e1; border-radius: 6px; padding: 6px;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateEdit:focus { border: 2px solid #2563eb; }
QPushButton { background: #2563eb; color: white; border: none; border-radius: 6px; padding: 8px 14px; font-weight: 600; }
QPushButton:hover { background: #1d4ed8; }
QPushButton[secondary='true'] { background: #e2e8f0; color: #172033; }
QPushButton[danger='true'] { background: #dc2626; }
QHeaderView::section { background: #f8cbad; color: #172033; padding: 7px; border: 1px solid #d7aa8a; font-weight: 700; }
QTabWidget::pane { border: 1px solid #dfe5ef; background: white; }
QTabBar::tab { background: #e9eef6; padding: 10px 18px; margin-right: 2px; }
QTabBar::tab:selected { background: #2563eb; color: white; }
"""

DARK = """
QWidget { font-family: 'Segoe UI'; font-size: 10pt; color: #e5e7eb; background: #111827; }
QMainWindow, QDialog { background: #111827; }
QFrame#card { background: #1f2937; border: 1px solid #374151; border-radius: 10px; }
QLineEdit, QTextEdit, QComboBox, QDateEdit, QSpinBox, QDoubleSpinBox, QTableWidget {
  background: #1f2937; color: #f9fafb; border: 1px solid #4b5563; border-radius: 6px; padding: 6px;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus, QDateEdit:focus { border: 2px solid #60a5fa; }
QPushButton { background: #2563eb; color: white; border: none; border-radius: 6px; padding: 8px 14px; font-weight: 600; }
QPushButton:hover { background: #3b82f6; }
QPushButton[secondary='true'] { background: #374151; color: #f9fafb; }
QPushButton[danger='true'] { background: #b91c1c; }
QHeaderView::section { background: #7c4a2e; color: white; padding: 7px; border: 1px solid #9a6546; font-weight: 700; }
QTabWidget::pane { border: 1px solid #374151; background: #1f2937; }
QTabBar::tab { background: #374151; padding: 10px 18px; margin-right: 2px; }
QTabBar::tab:selected { background: #2563eb; color: white; }
"""
