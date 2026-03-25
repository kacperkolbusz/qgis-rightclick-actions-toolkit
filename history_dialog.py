"""
RAT History Panel for Right-click Actions Toolkit

This module provides the user interface for viewing and managing the history
of actions performed by the plugin. It displays a list of all recorded actions
with timestamps and provides undo/redo functionality for supported actions.

The panel is implemented as a QDockWidget for seamless integration with QGIS.
"""

from qgis.PyQt.QtWidgets import (
    QDockWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QHeaderView, QMessageBox, QFrame, QGroupBox,
    QTextEdit, QSplitter, QWidget, QToolBar, QAction, QMenu,
    QFileDialog, QAbstractItemView, QSizePolicy
)
from qgis.PyQt.QtCore import Qt, QSize
from qgis.PyQt.QtGui import QFont, QColor, QIcon

from .history_manager import HistoryManager, get_history_manager


# Singleton instance for the history panel
_history_panel_instance = None


def get_history_panel(iface):
    """
    Get or create the singleton history panel instance.
    
    Args:
        iface: QGIS interface instance
        
    Returns:
        HistoryPanel: The singleton history panel instance
    """
    global _history_panel_instance
    if _history_panel_instance is None:
        _history_panel_instance = HistoryPanel(iface)
    return _history_panel_instance


def destroy_history_panel():
    """
    Destroy the singleton history panel instance.
    Call this when unloading the plugin.
    """
    global _history_panel_instance
    if _history_panel_instance is not None:
        # Remove from main window if added
        if _history_panel_instance._added_to_main_window:
            _history_panel_instance.iface.removeDockWidget(_history_panel_instance)
        _history_panel_instance.setParent(None)
        _history_panel_instance.deleteLater()
        _history_panel_instance = None


class HistoryPanel(QDockWidget):
    """
    Dock widget panel for viewing and managing the plugin action history.
    
    Features:
    - Displays all recorded actions with timestamps
    - Shows action details including affected layers and features
    - Provides undo/redo buttons for supported actions
    - Allows exporting individual history entries
    - Supports clearing history
    - Docks within QGIS main window
    """
    
    def __init__(self, iface):
        """Initialize the history panel."""
        super().__init__("RAT History Manager")
        
        self.iface = iface
        self.history_manager = get_history_manager()
        self.selected_entry = None
        self._added_to_main_window = False
        
        # Set dock widget properties
        self.setObjectName("RATHistoryPanel")
        self.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea | Qt.BottomDockWidgetArea)
        self.setMinimumWidth(400)
        self.setMinimumHeight(300)
        
        # Create main widget container
        self.main_widget = QWidget()
        self.setWidget(self.main_widget)
        
        self._setup_ui()
        self._connect_signals()
        self._refresh_table()
    
    def _setup_ui(self):
        """Set up the user interface."""
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setSpacing(10)
        main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Header
        header_layout = QHBoxLayout()
        
        title_label = QLabel("Action History")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)
        
        header_layout.addStretch()
        
        # Entry count label
        self.count_label = QLabel("0 entries")
        self.count_label.setStyleSheet("color: #666;")
        header_layout.addWidget(self.count_label)
        
        main_layout.addLayout(header_layout)
        
        # Toolbar
        toolbar_layout = QHBoxLayout()
        
        self.undo_btn = QPushButton("↶ Undo Selected")
        self.undo_btn.setEnabled(False)
        self.undo_btn.setToolTip("Undo the selected action")
        self.undo_btn.clicked.connect(self._on_undo_clicked)
        toolbar_layout.addWidget(self.undo_btn)
        
        self.redo_btn = QPushButton("↷ Redo")
        self.redo_btn.setEnabled(False)
        self.redo_btn.setToolTip("Redo the last undone action")
        self.redo_btn.clicked.connect(self._on_redo_clicked)
        toolbar_layout.addWidget(self.redo_btn)
        
        toolbar_layout.addSpacing(20)
        
        self.export_btn = QPushButton("📤 Export Entry")
        self.export_btn.setEnabled(False)
        self.export_btn.setToolTip("Export the selected entry to a JSON file")
        self.export_btn.clicked.connect(self._on_export_clicked)
        toolbar_layout.addWidget(self.export_btn)
        
        toolbar_layout.addStretch()
        
        self.refresh_btn = QPushButton("🔄 Refresh")
        self.refresh_btn.setToolTip("Refresh the history list")
        self.refresh_btn.clicked.connect(self._refresh_table)
        toolbar_layout.addWidget(self.refresh_btn)
        
        self.clear_btn = QPushButton("🗑 Clear History")
        self.clear_btn.setToolTip("Clear all history entries")
        self.clear_btn.clicked.connect(self._on_clear_clicked)
        toolbar_layout.addWidget(self.clear_btn)
        
        main_layout.addLayout(toolbar_layout)
        
        # Splitter for table and details
        splitter = QSplitter(Qt.Vertical)
        
        # History table
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Timestamp", "Action", "Description", "Layers", 
            "Features", "Status", "Undoable"
        ])
        
        # Table settings
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # Column widths
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # Timestamp
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)  # Action
        header.setSectionResizeMode(2, QHeaderView.Stretch)          # Description
        header.setSectionResizeMode(3, QHeaderView.ResizeToContents)  # Layers
        header.setSectionResizeMode(4, QHeaderView.ResizeToContents)  # Features
        header.setSectionResizeMode(5, QHeaderView.ResizeToContents)  # Status
        header.setSectionResizeMode(6, QHeaderView.ResizeToContents)  # Undoable
        
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)
        
        splitter.addWidget(self.table)
        
        # Details panel
        details_group = QGroupBox("Entry Details")
        details_layout = QVBoxLayout(details_group)
        
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setMaximumHeight(200)
        self.details_text.setPlaceholderText("Select an entry to view details...")
        details_layout.addWidget(self.details_text)
        
        splitter.addWidget(details_group)
        
        # Set splitter sizes
        splitter.setSizes([500, 200])
        
        main_layout.addWidget(splitter)
    
    def _connect_signals(self):
        """Connect to history manager signals."""
        self.history_manager.history_changed.connect(self._refresh_table)
        self.history_manager.undo_performed.connect(self._on_undo_performed)
        self.history_manager.redo_performed.connect(self._on_redo_performed)
    
    def _refresh_table(self):
        """Refresh the history table with current entries."""
        self.table.setRowCount(0)
        
        entries = self.history_manager.list_entries()
        
        # Display in reverse order (most recent first)
        for entry in reversed(entries):
            row = self.table.rowCount()
            self.table.insertRow(row)
            
            # Timestamp
            timestamp_item = QTableWidgetItem(entry.get_formatted_timestamp())
            timestamp_item.setData(Qt.UserRole, entry.entry_id)
            self.table.setItem(row, 0, timestamp_item)
            
            # Action name
            action_item = QTableWidgetItem(entry.action_name)
            action_item.setFont(QFont("", -1, QFont.Bold))
            self.table.setItem(row, 1, action_item)
            
            # Description
            desc_item = QTableWidgetItem(entry.description[:100] + "..." if len(entry.description) > 100 else entry.description)
            desc_item.setToolTip(entry.description)
            self.table.setItem(row, 2, desc_item)
            
            # Layers
            layers_item = QTableWidgetItem(entry.get_layers_summary())
            self.table.setItem(row, 3, layers_item)
            
            # Features count
            features_item = QTableWidgetItem(str(entry.get_features_count()))
            features_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 4, features_item)
            
            # Status
            status_item = QTableWidgetItem(entry.status.upper())
            if entry.status == "ok":
                status_item.setForeground(QColor("#28a745"))
            elif entry.status == "undone":
                status_item.setForeground(QColor("#6c757d"))
            elif entry.status == "failed":
                status_item.setForeground(QColor("#dc3545"))
            elif entry.status == "partial":
                status_item.setForeground(QColor("#ffc107"))
            self.table.setItem(row, 5, status_item)
            
            # Undoable
            if entry.can_undo:
                if entry.is_undone:
                    undo_item = QTableWidgetItem("↷ Redoable")
                    undo_item.setForeground(QColor("#17a2b8"))
                else:
                    undo_item = QTableWidgetItem("✓ Yes")
                    undo_item.setForeground(QColor("#28a745"))
            else:
                undo_item = QTableWidgetItem("— No")
                undo_item.setForeground(QColor("#6c757d"))
            undo_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 6, undo_item)
        
        # Update count label
        self.count_label.setText(f"{len(entries)} entries")
        
        # Update redo button state
        self.redo_btn.setEnabled(len(self.history_manager.get_redoable_entries()) > 0)
        
        # Clear selection
        self._on_selection_changed()
    
    def _on_selection_changed(self):
        """Handle table selection change."""
        selected_rows = self.table.selectionModel().selectedRows()
        
        if not selected_rows:
            self.selected_entry = None
            self.undo_btn.setEnabled(False)
            self.export_btn.setEnabled(False)
            self.details_text.clear()
            return
        
        row = selected_rows[0].row()
        entry_id = self.table.item(row, 0).data(Qt.UserRole)
        self.selected_entry = self.history_manager.get_entry(entry_id)
        
        if self.selected_entry:
            # Update button states
            can_undo, reason = self.history_manager.can_undo(entry_id)
            self.undo_btn.setEnabled(can_undo)
            if not can_undo and reason:
                self.undo_btn.setToolTip(f"Cannot undo: {reason}")
            else:
                self.undo_btn.setToolTip("Undo the selected action")
            
            self.export_btn.setEnabled(True)
            
            # Update details panel
            self._update_details_panel()
    
    def _update_details_panel(self):
        """Update the details panel with selected entry information."""
        if not self.selected_entry:
            self.details_text.clear()
            return
        
        entry = self.selected_entry
        
        details = []
        details.append(f"<h3>{entry.action_name}</h3>")
        details.append(f"<p><b>Entry ID:</b> {entry.entry_id}</p>")
        details.append(f"<p><b>Timestamp:</b> {entry.get_formatted_timestamp()}</p>")
        details.append(f"<p><b>Action ID:</b> {entry.action_id}</p>")
        details.append(f"<p><b>Description:</b> {entry.description}</p>")
        details.append(f"<p><b>Undo Type:</b> {entry.undo_type}</p>")
        details.append(f"<p><b>Can Undo:</b> {'Yes' if entry.can_undo else 'No'}</p>")
        details.append(f"<p><b>Is Undone:</b> {'Yes' if entry.is_undone else 'No'}</p>")
        details.append(f"<p><b>Status:</b> {entry.status}</p>")
        details.append(f"<p><b>Atomic:</b> {'Yes' if entry.atomic else 'No'}</p>")
        details.append(f"<p><b>Payload Size:</b> {entry.payload_size_bytes:,} bytes</p>")
        
        if entry.layers:
            details.append("<p><b>Affected Layers:</b></p><ul>")
            for layer in entry.layers:
                details.append(f"<li>{layer.get('layer_name', 'Unknown')} ({layer.get('layer_id', 'N/A')[:8]}...)</li>")
            details.append("</ul>")
        
        if entry.features:
            details.append(f"<p><b>Affected Features:</b> {len(entry.features)}</p>")
        
        if entry.meta:
            details.append("<p><b>Metadata:</b></p><pre>")
            import json
            details.append(json.dumps(entry.meta, indent=2))
            details.append("</pre>")
        
        self.details_text.setHtml("".join(details))
    
    def _on_cell_double_clicked(self, row, column):
        """Handle double-click on a cell."""
        entry_id = self.table.item(row, 0).data(Qt.UserRole)
        entry = self.history_manager.get_entry(entry_id)
        
        if entry and entry.can_undo and not entry.is_undone:
            self._on_undo_clicked()
    
    def _on_undo_clicked(self):
        """Handle undo button click."""
        if not self.selected_entry:
            return
        
        # Confirm undo
        reply = QMessageBox.question(
            self,
            "Confirm Undo",
            f"Are you sure you want to undo '{self.selected_entry.action_name}'?\n\n"
            f"Description: {self.selected_entry.description}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            success, message = self.history_manager.undo(self.selected_entry.entry_id)
            
            if success:
                QMessageBox.information(self, "Undo Successful", message)
            else:
                QMessageBox.warning(self, "Undo Failed", message)
    
    def _on_redo_clicked(self):
        """Handle redo button click."""
        success, message = self.history_manager.redo()
        
        if success:
            QMessageBox.information(self, "Redo Successful", message)
        else:
            QMessageBox.warning(self, "Redo Failed", message)
    
    def _on_export_clicked(self):
        """Handle export button click."""
        if not self.selected_entry:
            return
        
        # Get save path
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export History Entry",
            f"history_entry_{self.selected_entry.entry_id[:8]}.json",
            "JSON Files (*.json)"
        )
        
        if file_path:
            if self.history_manager.export_entry(self.selected_entry.entry_id, file_path):
                QMessageBox.information(self, "Export Successful", f"Entry exported to:\n{file_path}")
            else:
                QMessageBox.warning(self, "Export Failed", "Failed to export the history entry.")
    
    def _on_clear_clicked(self):
        """Handle clear history button click."""
        reply = QMessageBox.warning(
            self,
            "Clear History",
            "Are you sure you want to clear all history entries?\n\n"
            "This action cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.history_manager.clear_history()
            QMessageBox.information(self, "History Cleared", "All history entries have been cleared.")
    
    def _on_undo_performed(self, entry_id, success):
        """Handle undo performed signal."""
        self._refresh_table()
    
    def _on_redo_performed(self, entry_id, success):
        """Handle redo performed signal."""
        self._refresh_table()
