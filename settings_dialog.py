"""
Settings Dialog for Right-click Utilities and Shortcuts Hub

This module provides a settings dialog that allows users to enable/disable
individual right-click actions and configure the plugin behavior.
"""

from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, 
    QPushButton, QGroupBox, QScrollArea, QWidget, QMessageBox,
    QTabWidget, QTabBar, QFrame, QLineEdit, QSpinBox, QDoubleSpinBox,
    QComboBox, QFileDialog, QColorDialog, QSlider, QTextEdit,
    QSplitter, QTreeWidget, QTreeWidgetItem, QHeaderView
)
from qgis.PyQt.QtCore import Qt, QSettings, pyqtSignal
from qgis.PyQt.QtGui import QFont, QColor


class CollapsibleGroupWidget(QFrame):
    """
    A collapsible widget for displaying groups of items (categories or subcategories).
    Can be nested for hierarchical organization.
    """
    
    def __init__(self, title, parent=None, is_main_category=False, action_count=0):
        super().__init__(parent)
        self.title = title
        self.is_main_category = is_main_category
        self.action_count = action_count
        self.is_expanded = False  # Start collapsed by default
        self.content_widget = None
        self.init_ui()
    
    def init_ui(self):
        """Initialize the collapsible group widget UI."""
        self.setFrameStyle(QFrame.StyledPanel)
        
        # Different styling for main categories vs subcategories
        if self.is_main_category:
            self.setStyleSheet("""
                QFrame { 
                    border: 2px solid #4CAF50; 
                    border-radius: 6px; 
                    margin: 4px 0px; 
                    padding: 4px; 
                    background-color: #f1f8f4;
                }
                QFrame:hover {
                    background-color: #e8f5e9;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame { 
                    border: 1px solid #2196F3; 
                    border-radius: 4px; 
                    margin: 2px 0px; 
                    padding: 4px; 
                    background-color: #e3f2fd;
                }
                QFrame:hover {
                    background-color: #bbdefb;
                }
            """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)
        
        # Header row with expand button and title
        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)
        
        # Expand/collapse button
        self.expand_btn = QPushButton("▶" if not self.is_expanded else "▼")
        self.expand_btn.setFixedSize(24, 24)
        self.expand_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
                font-size: 12px;
                font-weight: bold;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.1);
                border-radius: 3px;
            }
        """)
        self.expand_btn.clicked.connect(self.toggle_expanded)
        header_layout.addWidget(self.expand_btn)
        
        # Title label with count
        title_text = self.title
        if self.action_count > 0:
            title_text = f"{self.title} ({self.action_count})"
        title_label = QLabel(title_text)
        title_font = QFont()
        title_font.setBold(True)
        if self.is_main_category:
            title_font.setPointSize(12)
        else:
            title_font.setPointSize(11)
        title_label.setFont(title_font)
        header_layout.addWidget(title_label)
        header_layout.addStretch()
        
        main_layout.addLayout(header_layout)
        
        # Content widget container
        self.content_widget = QWidget()
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(20, 4, 4, 4)  # Indent subcategories
        self.content_layout.setSpacing(4)
        main_layout.addWidget(self.content_widget)
        
        # Initially hide content (collapsed by default)
        self.content_widget.setVisible(self.is_expanded)
    
    def add_content_widget(self, widget):
        """Add a widget to the content area."""
        self.content_layout.addWidget(widget)
    
    def toggle_expanded(self):
        """Toggle the expanded/collapsed state."""
        self.is_expanded = not self.is_expanded
        
        # Show/hide the content widget container
        self.content_widget.setVisible(self.is_expanded)
        
        # Update button icon
        if self.is_expanded:
            self.expand_btn.setText("▼")
        else:
            self.expand_btn.setText("▶")


class CollapsibleActionWidget(QFrame):
    """
    A collapsible widget for displaying action settings.
    Shows only checkbox and name when collapsed, full details when expanded.
    """
    
    def __init__(self, action, checkbox, description_label, settings_button, parent=None):
        super().__init__(parent)
        self.action = action
        self.checkbox = checkbox
        self.description_label = description_label
        self.settings_button = settings_button
        self.is_expanded = False
        self.init_ui()
    
    def init_ui(self):
        """Initialize the collapsible widget UI."""
        self.setFrameStyle(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame { 
                border: 1px solid #ddd; 
                border-radius: 4px; 
                margin: 2px; 
                padding: 4px; 
                background-color: #fafafa;
            }
            QFrame:hover {
                background-color: #f5f5f5;
            }
        """)
        
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(4)
        
        # Header row with expand button, checkbox, and name
        header_layout = QHBoxLayout()
        header_layout.setSpacing(6)
        
        # Expand/collapse button
        self.expand_btn = QPushButton("▶")
        self.expand_btn.setFixedSize(20, 20)
        self.expand_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background-color: transparent;
                font-size: 10px;
                padding: 0px;
            }
            QPushButton:hover {
                background-color: #e0e0e0;
                border-radius: 2px;
            }
        """)
        self.expand_btn.clicked.connect(self.toggle_expanded)
        header_layout.addWidget(self.expand_btn)
        
        # Checkbox (already created, just add it)
        header_layout.addWidget(self.checkbox)
        header_layout.addStretch()
        
        main_layout.addLayout(header_layout)
        
        # Content widget (description and settings) - initially hidden
        self.content_widget = QWidget()
        content_layout = QVBoxLayout(self.content_widget)
        content_layout.setContentsMargins(26, 0, 0, 0)  # Indent to align with checkbox text
        content_layout.setSpacing(4)
        
        if self.description_label:
            content_layout.addWidget(self.description_label)
        
        if self.settings_button:
            content_layout.addWidget(self.settings_button)
        
        main_layout.addWidget(self.content_widget)
        
        # Initially collapsed
        self.content_widget.setVisible(False)
    
    def toggle_expanded(self):
        """Toggle the expanded/collapsed state."""
        self.is_expanded = not self.is_expanded
        self.content_widget.setVisible(self.is_expanded)
        
        # Update button icon
        if self.is_expanded:
            self.expand_btn.setText("▼")
        else:
            self.expand_btn.setText("▶")


class ActionSettingsWidget(QWidget):
    """
    Widget for configuring individual action settings.
    """
    
    setting_changed = pyqtSignal(str, str, object)  # action_id, setting_name, value
    
    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.action = action
        self.setting_widgets = {}
        self.init_ui()
    
    def init_ui(self):
        """Initialize the settings UI for this action."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Action title
        title_label = QLabel(f"Settings for: {self.action.name}")
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        title_label.setFont(title_font)
        layout.addWidget(title_label)
        
        # Action description
        if self.action.description:
            desc_label = QLabel(self.action.description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #666; margin-bottom: 10px;")
            layout.addWidget(desc_label)
        
        # Settings schema
        schema = self.action.get_settings_schema()
        if not schema:
            no_settings_label = QLabel("This action has no customizable settings.")
            no_settings_label.setStyleSheet("color: #999; font-style: italic;")
            layout.addWidget(no_settings_label)
            return
        
        # Create settings widgets
        for setting_name, setting_def in schema.items():
            self.create_setting_widget(setting_name, setting_def, layout)
        
        # Add reset to defaults button
        reset_layout = QHBoxLayout()
        reset_layout.addStretch()
        
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff9800;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f57c00;
            }
            QPushButton:pressed {
                background-color: #ef6c00;
            }
        """)
        reset_btn.clicked.connect(self.reset_to_defaults)
        reset_layout.addWidget(reset_btn)
        
        layout.addLayout(reset_layout)
        
        # Add stretch
        layout.addStretch()
    
    def create_setting_widget(self, setting_name, setting_def, layout):
        """Create a widget for a specific setting."""
        setting_type = setting_def.get('type', 'str')
        label_text = setting_def.get('label', setting_name)
        description = setting_def.get('description', '')
        default_value = setting_def.get('default')
        
        # Get current value
        current_value = self.action.get_setting(setting_name, default_value)
        
        # Create label
        label = QLabel(label_text)
        label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        layout.addWidget(label)
        
        # Create description if available
        if description:
            desc_label = QLabel(description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #666; font-size: 11px; margin-bottom: 5px;")
            layout.addWidget(desc_label)
        
        # Create appropriate widget based on type
        if setting_type == 'bool':
            widget = QCheckBox()
            widget.setChecked(bool(current_value))
            widget.toggled.connect(lambda checked: self.on_setting_changed(setting_name, checked))
            
        elif setting_type in ['int', 'float']:
            if setting_type == 'int':
                widget = QSpinBox()
                widget.setRange(int(setting_def.get('min', -999999)), int(setting_def.get('max', 999999)))
                widget.setValue(int(current_value))
            else:
                widget = QDoubleSpinBox()
                widget.setRange(float(setting_def.get('min', -999999.0)), float(setting_def.get('max', 999999.0)))
                widget.setValue(float(current_value))
            
            step = setting_def.get('step', 1)
            widget.setSingleStep(step)
            widget.valueChanged.connect(lambda value: self.on_setting_changed(setting_name, value))
            
        elif setting_type == 'choice':
            widget = QComboBox()
            options = setting_def.get('options', [])
            widget.addItems(options)
            if current_value in options:
                widget.setCurrentText(str(current_value))
            widget.currentTextChanged.connect(lambda text: self.on_setting_changed(setting_name, text))
            
        elif setting_type == 'str':
            widget = QLineEdit()
            widget.setText(str(current_value))
            widget.textChanged.connect(lambda text: self.on_setting_changed(setting_name, text))
            
        elif setting_type == 'file_path':
            widget = QLineEdit()
            widget.setText(str(current_value))
            widget.setReadOnly(True)
            
            # Create file picker button
            file_layout = QHBoxLayout()
            file_layout.addWidget(widget)
            
            browse_btn = QPushButton("Browse...")
            browse_btn.clicked.connect(lambda: self.browse_file(setting_name, widget))
            file_layout.addWidget(browse_btn)
            
            file_widget = QWidget()
            file_widget.setLayout(file_layout)
            layout.addWidget(file_widget)
            self.setting_widgets[setting_name] = file_widget
            return
            
        elif setting_type == 'directory_path':
            widget = QLineEdit()
            widget.setText(str(current_value))
            widget.setReadOnly(True)
            
            # Create directory picker button
            dir_layout = QHBoxLayout()
            dir_layout.addWidget(widget)
            
            browse_btn = QPushButton("Browse...")
            browse_btn.clicked.connect(lambda: self.browse_directory(setting_name, widget))
            dir_layout.addWidget(browse_btn)
            
            dir_widget = QWidget()
            dir_widget.setLayout(dir_layout)
            layout.addWidget(dir_widget)
            self.setting_widgets[setting_name] = dir_widget
            return
            
        elif setting_type == 'color':
            widget = QPushButton()
            color = QColor(str(current_value))
            widget.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc;")
            widget.setText(color.name())
            widget.clicked.connect(lambda: self.choose_color(setting_name, widget))
            
        else:
            # Fallback to text input
            widget = QLineEdit()
            widget.setText(str(current_value))
            widget.textChanged.connect(lambda text: self.on_setting_changed(setting_name, text))
        
        layout.addWidget(widget)
        self.setting_widgets[setting_name] = widget
    
    def on_setting_changed(self, setting_name, value):
        """Handle setting value change."""
        # Validate the setting
        is_valid, error_msg = self.action.validate_setting(setting_name, value)
        
        if is_valid:
            # Set the setting
            self.action.set_setting(setting_name, value)
            self.setting_changed.emit(self.action.action_id, setting_name, value)
        else:
            # Show error message
            QMessageBox.warning(self, "Invalid Setting", f"Invalid value for {setting_name}: {error_msg}")
    
    def browse_file(self, setting_name, line_edit):
        """Browse for a file."""
        current_path = line_edit.text()
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"Select file for {setting_name}", current_path
        )
        if file_path:
            line_edit.setText(file_path)
            self.on_setting_changed(setting_name, file_path)
    
    def browse_directory(self, setting_name, line_edit):
        """Browse for a directory."""
        current_path = line_edit.text()
        dir_path = QFileDialog.getExistingDirectory(
            self, f"Select directory for {setting_name}", current_path
        )
        if dir_path:
            line_edit.setText(dir_path)
            self.on_setting_changed(setting_name, dir_path)
    
    def choose_color(self, setting_name, button):
        """Choose a color."""
        current_color = QColor(button.text())
        color = QColorDialog.getColor(current_color, self, f"Choose color for {setting_name}")
        if color.isValid():
            button.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc;")
            button.setText(color.name())
            self.on_setting_changed(setting_name, color.name())
    
    def reset_to_defaults(self):
        """Reset all settings for this action to their default values."""
        reply = QMessageBox.question(
            self,
            "Reset to Defaults",
            f"Are you sure you want to reset all settings for '{self.action.name}' to their default values?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Reset settings in the action
            self.action.reset_settings_to_defaults()
            
            # Refresh all widgets with default values
            schema = self.action.get_settings_schema()
            for setting_name, setting_def in schema.items():
                default_value = setting_def.get('default')
                if default_value is not None:
                    self.update_setting_widget(setting_name, default_value)
            
            # Show confirmation
            QMessageBox.information(
                self,
                "Settings Reset",
                f"All settings for '{self.action.name}' have been reset to their default values."
            )
    
    def update_setting_widget(self, setting_name, value):
        """Update a setting widget with a new value."""
        widget = self.setting_widgets.get(setting_name)
        if not widget:
            return
        
        # Update widget based on its type
        if isinstance(widget, QCheckBox):
            widget.setChecked(bool(value))
        elif isinstance(widget, (QSpinBox, QDoubleSpinBox)):
            widget.setValue(value)
        elif isinstance(widget, QComboBox):
            if str(value) in [widget.itemText(i) for i in range(widget.count())]:
                widget.setCurrentText(str(value))
        elif isinstance(widget, QLineEdit):
            widget.setText(str(value))
        elif isinstance(widget, QPushButton) and hasattr(widget, 'setStyleSheet'):
            # Color button
            color = QColor(str(value))
            widget.setStyleSheet(f"background-color: {color.name()}; border: 1px solid #ccc;")
            widget.setText(color.name())


class ActionSettingsWindow(QDialog):
    """
    Separate window for configuring individual action settings.
    """
    
    def __init__(self, action, parent=None):
        super().__init__(parent)
        self.action = action
        self.init_ui()
    
    def init_ui(self):
        """Initialize the settings window UI."""
        self.setWindowTitle(f"Settings for: {self.action.name}")
        self.setModal(True)
        self.resize(500, 400)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        
        # Title
        title_label = QLabel(f"Configure Settings for: {self.action.name}")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # Action description
        if self.action.description:
            desc_label = QLabel(self.action.description)
            desc_label.setWordWrap(True)
            desc_label.setStyleSheet("color: #666; margin-bottom: 15px; padding: 10px; background-color: #f5f5f5; border-radius: 4px;")
            main_layout.addWidget(desc_label)
        
        # Warning label
        warning_label = QLabel("⚠️ These settings are for advanced users. Incorrect values may cause the action to malfunction.")
        warning_label.setWordWrap(True)
        warning_label.setStyleSheet("""
            color: #d84315;
            font-weight: bold;
            font-size: 12px;
            background-color: #ffebee;
            border: 1px solid #ffcdd2;
            border-radius: 4px;
            padding: 10px;
            margin-bottom: 15px;
        """)
        main_layout.addWidget(warning_label)
        
        # Create scroll area for settings
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # Create settings widget
        settings_widget = ActionSettingsWidget(self.action)
        settings_widget.setting_changed.connect(self.on_setting_changed)
        
        scroll_area.setWidget(settings_widget)
        main_layout.addWidget(scroll_area)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        # Reset to defaults button
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff9800;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #f57c00;
            }
            QPushButton:pressed {
                background-color: #ef6c00;
            }
        """)
        reset_btn.clicked.connect(self.reset_to_defaults)
        button_layout.addWidget(reset_btn)
        
        button_layout.addStretch()
        
        # Close button
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196f3;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
            QPushButton:pressed {
                background-color: #1565c0;
            }
        """)
        close_btn.clicked.connect(self.accept)
        button_layout.addWidget(close_btn)
        
        main_layout.addLayout(button_layout)
    
    def on_setting_changed(self, action_id, setting_name, value):
        """Handle setting changes."""
        # Settings are automatically saved by the ActionSettingsWidget
        pass
    
    def reset_to_defaults(self):
        """Reset all settings to defaults."""
        reply = QMessageBox.question(
            self,
            "Reset to Defaults",
            f"Are you sure you want to reset all settings for '{self.action.name}' to their default values?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            # Reset settings in the action
            self.action.reset_settings_to_defaults()
            
            # Close and reopen the window to refresh
            self.accept()
            self.init_ui()
            
            # Show confirmation
            QMessageBox.information(
                self,
                "Settings Reset",
                f"All settings for '{self.action.name}' have been reset to their default values."
            )


class SettingsDialog(QDialog):
    """
    Settings dialog for configuring right-click actions.
    """
    
    def __init__(self, action_registry, parent=None):
        """
        Initialize the settings dialog.
        
        Args:
            action_registry (ActionRegistry): The action registry to configure
            parent: Parent widget
        """
        super().__init__(parent)
        self.action_registry = action_registry
        self.checkboxes = {}
        self.settings = QSettings()
        self.click_type_to_tab_index = {}  # Map click_type to tab index
        self.tab_names = {}  # Store original tab names
        self.all_tab_index = None  # Index of the "All" tab
        self.init_ui()
        
    def init_ui(self):
        """Initialize the user interface."""
        self.setWindowTitle("Right-click Utilities - Settings")
        self.setModal(True)
        self.resize(600, 500)
        
        # Main layout
        main_layout = QVBoxLayout()
        
        # Title
        title_label = QLabel("Configure Right-click Actions")
        title_font = QFont()
        title_font.setPointSize(14)
        title_font.setBold(True)
        title_label.setFont(title_font)
        title_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(title_label)
        
        # Description
        desc_label = QLabel(
            "Select which actions should appear in the right-click context menu "
            "for each feature type. Actions are organized by the type of feature they work with.\n\n"
            "💡 Tip: Click the '⚙️ Configure Settings (Advanced Users Only)' button under each action to customize its behavior in a separate window."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; margin-bottom: 10px;")
        main_layout.addWidget(desc_label)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Add General tab first
        general_tab = self.create_general_tab()
        self.tab_widget.addTab(general_tab, "General")
        
        # Add "All" tab after General
        all_tab = self.create_all_actions_tab()
        self.all_tab_index = 1  # Index 1 (after General at 0)
        total, enabled = self.get_all_actions_counts()
        tab_name_with_counts = f"All ({enabled}/{total})"
        self.tab_widget.addTab(all_tab, tab_name_with_counts)
        
        main_layout.addWidget(self.tab_widget)
        
        # Button layout
        button_layout = QHBoxLayout()
        
        # Select All button
        select_all_btn = QPushButton("Select All")
        select_all_btn.clicked.connect(self.select_all)
        button_layout.addWidget(select_all_btn)
        
        # Deselect All button
        deselect_all_btn = QPushButton("Deselect All")
        deselect_all_btn.clicked.connect(self.deselect_all)
        button_layout.addWidget(deselect_all_btn)
        
        button_layout.addStretch()
        
        # About button
        about_btn = QPushButton("About")
        about_btn.clicked.connect(self.show_about)
        button_layout.addWidget(about_btn)
        
        # Reset to Defaults button
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self.reset_to_defaults)
        button_layout.addWidget(reset_btn)
        
        # Cancel button
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        button_layout.addWidget(cancel_btn)
        
        # Save button
        save_btn = QPushButton("Save")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self.accept)
        button_layout.addWidget(save_btn)
        
        main_layout.addLayout(button_layout)
        
        self.setLayout(main_layout)
    
    def get_actions_for_click_type(self, click_type):
        """
        Get all actions that support a specific click type.
        
        Args:
            click_type (str): The click type (e.g., 'multipoint', 'multiline', etc.)
            
        Returns:
            list: List of actions that support this click type
        """
        all_actions = self.action_registry.get_all_actions()
        supported_actions = []
        
        for action in all_actions:
            if click_type == 'universal':
                # For universal tab, only show actions that support universal click type
                if action.supports_click_type('universal') or 'universal' in action.supported_click_types:
                    supported_actions.append(action)
            else:
                # For other tabs, show actions that support this specific click type
                # but exclude universal actions (they should only appear in universal tab)
                if (action.supports_click_type(click_type) and 
                    not action.supports_click_type('universal') and 
                    'universal' not in action.supported_click_types):
                    supported_actions.append(action)
        
        return supported_actions
    
    def get_action_counts(self, click_type):
        """
        Get total and enabled action counts for a click type.
        
        Args:
            click_type (str): The click type
            
        Returns:
            tuple: (total_count, enabled_count)
        """
        actions = self.get_actions_for_click_type(click_type)
        total = len(actions)
        enabled = 0
        
        for action in actions:
            checkbox = self.checkboxes.get(action.action_id)
            if checkbox and checkbox.isChecked():
                enabled += 1
        
        return total, enabled
    
    def update_tab_name(self, click_type):
        """
        Update the tab name with current counts for a click type.
        
        Args:
            click_type (str): The click type to update
        """
        if click_type not in self.click_type_to_tab_index:
            return
        
        tab_index = self.click_type_to_tab_index[click_type]
        original_name = self.tab_names[click_type]
        total, enabled = self.get_action_counts(click_type)
        tab_name_with_counts = f"{original_name} ({enabled}/{total})"
        self.tab_widget.setTabText(tab_index, tab_name_with_counts)
    
    def update_all_tab_names(self):
        """Update all tab names with current counts."""
        # Update "All" tab
        if self.all_tab_index is not None:
            total, enabled = self.get_all_actions_counts()
            tab_name_with_counts = f"All ({enabled}/{total})"
            self.tab_widget.setTabText(self.all_tab_index, tab_name_with_counts)
        
        # Update click type tabs
        for click_type in self.click_type_to_tab_index.keys():
            self.update_tab_name(click_type)
    
    def get_all_actions_counts(self):
        """
        Get total and enabled action counts for all actions.
        
        Returns:
            tuple: (total_count, enabled_count)
        """
        all_actions = self.action_registry.get_all_actions()
        total = len(all_actions)
        enabled = 0
        
        for action in all_actions:
            checkbox = self.checkboxes.get(action.action_id)
            if checkbox and checkbox.isChecked():
                enabled += 1
        
        return total, enabled
    
    def create_general_tab(self):
        """
        Create the General settings tab.
        
        Returns:
            QWidget: The general tab widget
        """
        # Create main widget for the tab
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        
        # Add description
        desc_label = QLabel(
            "General settings for the Right-click Utilities plugin. "
            "These settings control the overall behavior of the plugin."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addWidget(desc_label)
        
        # Context Menu Settings group
        settings_group = QGroupBox("Context Menu Settings")
        settings_layout = QVBoxLayout(settings_group)
        
        # Copy Coordinates checkbox
        self.copy_coords_checkbox = QCheckBox("Show 'Copy Coordinates' in context menu")
        self.copy_coords_checkbox.setToolTip(
            "When enabled, the built-in QGIS 'Copy Coordinates' option will appear "
            "in the right-click context menu. When disabled, only the plugin's "
            "custom actions will be shown."
        )
        
        # Load current setting
        show_copy_coords = self.settings.value('rightclick_utilities/show_copy_coordinates', False, type=bool)
        self.copy_coords_checkbox.setChecked(show_copy_coords)
        
        settings_layout.addWidget(self.copy_coords_checkbox)
        
        # Add explanation
        explanation_label = QLabel(
            "By default, the plugin hides the built-in 'Copy Coordinates' option "
            "to provide a cleaner context menu experience. Enable this option if "
            "you want to restore the original QGIS behavior."
        )
        explanation_label.setWordWrap(True)
        explanation_label.setStyleSheet("color: #888; font-size: 11px; margin-top: 5px;")
        settings_layout.addWidget(explanation_label)
        
        layout.addWidget(settings_group)
        
        # Add stretch to push everything to the top
        layout.addStretch()
        
        return tab_widget
    
    def create_click_type_tab(self, click_type, tab_name):
        """
        Create a tab widget for a specific click type.
        
        Args:
            click_type (str): The click type (e.g., 'point', 'line', etc.)
            tab_name (str): Display name for the tab
            
        Returns:
            QWidget: The tab widget
        """
        # Create main widget for the tab
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        
        # Add description
        desc_text = f"Actions available when right-clicking on {tab_name.lower()}:"
        desc_label = QLabel(desc_text)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addWidget(desc_label)
        
        # Create scroll area for actions
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # Actions widget
        actions_widget = QWidget()
        actions_layout = QVBoxLayout(actions_widget)
        
        # Get actions that support this click type
        supported_actions = self.get_actions_for_click_type(click_type)
        
        if not supported_actions:
            no_actions_label = QLabel(f"No actions available for {tab_name.lower()}.")
            no_actions_label.setAlignment(Qt.AlignCenter)
            no_actions_label.setStyleSheet("color: #999; font-style: italic;")
            actions_layout.addWidget(no_actions_label)
        else:
            # Group actions by category
            categories = {}
            for action in supported_actions:
                category = action.category or 'Other'
                if category not in categories:
                    categories[category] = []
                categories[category].append(action)
            
            for category, actions in categories.items():
                # Create category group
                category_group = QGroupBox(category)
                category_layout = QVBoxLayout(category_group)
                
                for action in actions:
                    # Create checkbox for each action
                    checkbox = QCheckBox(action.name)
                    checkbox.setStyleSheet("QCheckBox { font-weight: bold; }")
                    
                    # Load saved setting or use current enabled state
                    saved_enabled = self.settings.value(f"RightClickUtilities/{action.action_id}", action.enabled, type=bool)
                    checkbox.setChecked(saved_enabled)
                    
                    # Store reference to checkbox
                    self.checkboxes[action.action_id] = checkbox
                    
                    # Connect checkbox to update tab name when toggled
                    checkbox.toggled.connect(lambda checked, ct=click_type: self.update_tab_name(ct))
                    # Also update "All" tab when any checkbox is toggled
                    checkbox.toggled.connect(lambda checked: self.update_all_tab_names())
                    
                    # Create description label
                    description_label = QLabel(action.description or 'No description available')
                    description_label.setWordWrap(True)
                    description_label.setStyleSheet("color: #666; font-size: 11px;")
                    
                    # Create settings button
                    settings_button = self.create_action_settings_button(action)
                    
                    # Create collapsible action widget
                    action_widget = CollapsibleActionWidget(
                        action, checkbox, description_label, settings_button
                    )
                    
                    # Add action widget to category layout
                    category_layout.addWidget(action_widget)
                
                actions_layout.addWidget(category_group)
        
        # Add stretch to push everything to the top
        actions_layout.addStretch()
        
        scroll_area.setWidget(actions_widget)
        layout.addWidget(scroll_area)
        
        return tab_widget
    
    def create_all_actions_tab(self):
        """
        Create the "All" tab that shows all actions organized hierarchically:
        - Main categories: Point RAT, Line RAT, Polygon RAT, Canvas RAT, Universal RAT
        - Subcategories: Analysis, Editing, Navigation, etc.
        - Actions within each subcategory
        
        Returns:
            QWidget: The "All" tab widget
        """
        # Create main widget for the tab
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        
        # Add description
        desc_label = QLabel(
            "All available actions organized by type (Point RAT, Line RAT, etc.) and category (Analysis, Editing, etc.). "
            "Click the arrows to expand/collapse sections. You can enable/disable actions and configure their settings from here."
        )
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("color: #666; margin-bottom: 10px;")
        layout.addWidget(desc_label)
        
        # Create scroll area for actions
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # Actions widget
        actions_widget = QWidget()
        actions_layout = QVBoxLayout(actions_widget)
        
        # Get all actions
        all_actions = self.action_registry.get_all_actions()
        
        if not all_actions:
            no_actions_label = QLabel("No actions available.")
            no_actions_label.setAlignment(Qt.AlignCenter)
            no_actions_label.setStyleSheet("color: #999; font-style: italic;")
            actions_layout.addWidget(no_actions_label)
        else:
            # Map click types to display names
            click_type_names = {
                'point': 'Point RAT',
                'multipoint': 'Point RAT',
                'line': 'Line RAT',
                'multiline': 'Line RAT',
                'polygon': 'Polygon RAT',
                'multipolygon': 'Polygon RAT',
                'canvas': 'Canvas RAT',
                'universal': 'Universal RAT'
            }
            
            # Group actions by main category (click type) first
            main_categories = {}
            for action in all_actions:
                # Determine main category based on supported click types
                main_category = None
                
                # Check for universal first
                if 'universal' in action.supported_click_types:
                    main_category = 'Universal RAT'
                # Check for canvas
                elif 'canvas' in action.supported_click_types:
                    main_category = 'Canvas RAT'
                # Check for polygon types
                elif any(ct in action.supported_click_types for ct in ['polygon', 'multipolygon']):
                    main_category = 'Polygon RAT'
                # Check for line types
                elif any(ct in action.supported_click_types for ct in ['line', 'multiline']):
                    main_category = 'Line RAT'
                # Check for point types
                elif any(ct in action.supported_click_types for ct in ['point', 'multipoint']):
                    main_category = 'Point RAT'
                else:
                    # Default to Other if no clear category
                    main_category = 'Other'
                
                if main_category not in main_categories:
                    main_categories[main_category] = []
                main_categories[main_category].append(action)
            
            # Sort main categories in a specific order
            category_order = ['Point RAT', 'Line RAT', 'Polygon RAT', 'Canvas RAT', 'Universal RAT', 'Other']
            sorted_main_categories = sorted(
                main_categories.keys(),
                key=lambda x: (category_order.index(x) if x in category_order else 999, x)
            )
            
            # Create main category groups
            for main_category in sorted_main_categories:
                actions = main_categories[main_category]
                total_actions_in_category = len(actions)  # Total count for main category
                
                # Group actions by subcategory (action.category)
                subcategories = {}
                for action in actions:
                    subcategory = action.category or 'Other'
                    if subcategory not in subcategories:
                        subcategories[subcategory] = []
                    subcategories[subcategory].append(action)
                
                # Sort subcategories alphabetically
                sorted_subcategories = sorted(subcategories.keys())
                
                # Create main category collapsible group with count
                main_category_group = CollapsibleGroupWidget(
                    main_category, 
                    is_main_category=True, 
                    action_count=total_actions_in_category
                )
                
                # Create subcategory groups within main category
                for subcategory in sorted_subcategories:
                    subcategory_actions = subcategories[subcategory]
                    subcategory_count = len(subcategory_actions)  # Count for subcategory
                    # Sort actions within subcategory by name
                    subcategory_actions.sort(key=lambda a: a.name)
                    
                    # Create subcategory collapsible group with count
                    subcategory_group = CollapsibleGroupWidget(
                        subcategory, 
                        is_main_category=False,
                        action_count=subcategory_count
                    )
                    
                    # Add actions to subcategory
                    for action in subcategory_actions:
                        # Check if checkbox already exists (from other tabs)
                        if action.action_id in self.checkboxes:
                            # Use existing checkbox state but create new widget for this tab
                            existing_checkbox = self.checkboxes[action.action_id]
                            saved_enabled = existing_checkbox.isChecked()
                        else:
                            # Load saved setting or use current enabled state
                            saved_enabled = self.settings.value(f"RightClickUtilities/{action.action_id}", action.enabled, type=bool)
                        
                        # Create checkbox for each action
                        checkbox = QCheckBox(action.name)
                        checkbox.setStyleSheet("QCheckBox { font-weight: bold; }")
                        checkbox.setChecked(saved_enabled)
                        
                        # Store reference to checkbox (will overwrite if exists, but that's ok)
                        self.checkboxes[action.action_id] = checkbox
                        
                        # Connect checkbox to update tab names when toggled
                        checkbox.toggled.connect(lambda checked: self.update_all_tab_names())
                        
                        # Create description label
                        description_label = QLabel(action.description or 'No description available')
                        description_label.setWordWrap(True)
                        description_label.setStyleSheet("color: #666; font-size: 11px;")
                        
                        # Create settings button
                        settings_button = self.create_action_settings_button(action)
                        
                        # Create collapsible action widget
                        action_widget = CollapsibleActionWidget(
                            action, checkbox, description_label, settings_button
                        )
                        
                        # Add action widget to subcategory group
                        subcategory_group.add_content_widget(action_widget)
                    
                    # Add subcategory group to main category group
                    main_category_group.add_content_widget(subcategory_group)
                
                # Add main category group to actions layout
                actions_layout.addWidget(main_category_group)
        
        # Add stretch to push everything to the top
        actions_layout.addStretch()
        
        scroll_area.setWidget(actions_widget)
        layout.addWidget(scroll_area)
        
        return tab_widget
    
    def create_action_settings_button(self, action):
        """
        Create a settings button for an action that opens settings in a separate window.
        
        Args:
            action: The action to create settings for
            
        Returns:
            QWidget: The settings button widget or None if no settings
        """
        schema = action.get_settings_schema()
        if not schema:
            return None
        
        # Create button layout
        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 5, 0, 5)
        
        # Create settings button
        settings_btn = QPushButton("⚙️ Configure Settings (Advanced Users Only)")
        settings_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff9800;
                color: white;
                border: none;
                padding: 6px 12px;
                border-radius: 3px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #f57c00;
            }
            QPushButton:pressed {
                background-color: #ef6c00;
            }
        """)
        settings_btn.clicked.connect(lambda: self.open_action_settings_window(action))
        
        button_layout.addWidget(settings_btn)
        button_layout.addStretch()
        
        # Create container widget
        button_widget = QWidget()
        button_widget.setLayout(button_layout)
        
        return button_widget
    
    def open_action_settings_window(self, action):
        """
        Open a separate window for configuring action settings.
        
        Args:
            action: The action to configure settings for
        """
        settings_window = ActionSettingsWindow(action, self)
        settings_window.exec_()
    
    def on_action_setting_changed(self, action_id, setting_name, value):
        """
        Handle action setting changes.
        
        Args:
            action_id (str): ID of the action
            setting_name (str): Name of the setting
            value: New value
        """
        # Settings are automatically saved by the ActionSettingsWidget
        # This method can be used for additional processing if needed
        pass
    
    def select_all(self):
        """Select all actions."""
        for checkbox in self.checkboxes.values():
            checkbox.setChecked(True)
        # Update all tab names after changes
        self.update_all_tab_names()
    
    def deselect_all(self):
        """Deselect all actions."""
        for checkbox in self.checkboxes.values():
            checkbox.setChecked(False)
        # Update all tab names after changes
        self.update_all_tab_names()
    
    def reset_to_defaults(self):
        """Reset all actions to their default enabled state."""
        reply = QMessageBox.question(
            self,
            "Reset to Defaults",
            "Are you sure you want to reset all actions to their default settings?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            for action in self.action_registry.get_all_actions():
                checkbox = self.checkboxes.get(action.action_id)
                if checkbox:
                    # Reset to original default enabled state (True for all actions)
                    checkbox.setChecked(True)
            # Update all tab names after changes
            self.update_all_tab_names()
    
    def show_about(self):
        """Show information about the plugin."""
        message = f"Right-click Utilities and Shortcuts Hub\n"
        message += f"Version 1.0.6\n\n"
        message += f"A universal right-click context menu plugin that automatically\n"
        message += f"detects features anywhere on the canvas.\n\n"
        message += f"Features:\n"
        message += f"• Universal detection system (no layer selection needed)\n"
        message += f"• Smart hierarchical menus for overlapping features\n"
        message += f"• Extended search tolerance (10px for points/lines)\n"
        message += f"• Modular action system\n\n"
        message += f"Right-click anywhere on the canvas to use!\n\n"
        message += f"Questions, suggestions? Contact me: kk.at.work@pm.me"
        
        QMessageBox.information(self, "About Right-click Utilities", message)
    
    def get_settings(self):
        """
        Get the current settings from the dialog.
        
        Returns:
            dict: Dictionary mapping action IDs to their enabled state
        """
        settings = {}
        for action_id, checkbox in self.checkboxes.items():
            settings[action_id] = checkbox.isChecked()
        return settings
    
    def apply_settings(self):
        """Apply the current settings to the action registry and save general settings."""
        # Apply action settings
        for action_id, checkbox in self.checkboxes.items():
            enabled = checkbox.isChecked()
            self.action_registry.set_action_enabled(action_id, enabled)
        
        # Apply general settings
        show_copy_coords = self.copy_coords_checkbox.isChecked()
        self.settings.setValue('rightclick_utilities/show_copy_coordinates', show_copy_coords)
