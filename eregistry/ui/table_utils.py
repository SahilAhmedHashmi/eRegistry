from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableWidget


def configure_resizable_columns(
    table: QTableWidget,
    default_widths: Sequence[int] | None = None,
) -> None:
    """Give a table Excel-style manually resizable columns."""

    header = table.horizontalHeader()

    # Users can drag header dividers to resize columns.
    header.setSectionResizeMode(QHeaderView.Interactive)
    header.setStretchLastSection(False)
    header.setMinimumSectionSize(60)
    header.setDefaultSectionSize(120)

    # Keep long labels readable instead of clipping their first/last letters.
    header.setMinimumHeight(52)
    header.setDefaultAlignment(Qt.AlignCenter | Qt.TextWordWrap)
    header.setTextElideMode(Qt.ElideNone)

    # Double-clicking a header divider automatically fits that column.
    header.sectionHandleDoubleClicked.connect(
        table.resizeColumnToContents
    )

    # Show a horizontal scrollbar whenever the columns exceed the screen.
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

    # Keep rows compact and show an ellipsis when content is clipped.
    table.setWordWrap(False)
    table.setTextElideMode(Qt.ElideRight)

    if default_widths:
        for column, width in enumerate(default_widths):
            if column < table.columnCount() and width > 0:
                table.setColumnWidth(column, width)