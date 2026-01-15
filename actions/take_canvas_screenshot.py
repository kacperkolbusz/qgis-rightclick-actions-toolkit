"""
Take Canvas Screenshot Action for Right-click Utilities and Shortcuts Hub

Takes a screenshot of the entire map canvas and saves it to C:\RAT_screenshots by default.
Works universally and operates silently without popup windows.
"""

from .base_action import BaseAction
from qgis.gui import QgsMapCanvas
from qgis.PyQt.QtWidgets import QApplication
from qgis.PyQt.QtCore import QDir
import os
import subprocess
import platform
from datetime import datetime


class TakeCanvasScreenshotAction(BaseAction):
    """Action to take a screenshot of the entire map canvas."""
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "take_canvas_screenshot"
        self.name = "Take Canvas Screenshot"
        self.category = "Export"
        self.description = "Take a screenshot of the entire map canvas and save it to C:\\RAT_screenshots by default. Saves with timestamped filename in PNG format. Works everywhere and operates silently without popup windows."
        self.enabled = True
        
        # Action scoping - universal action that works everywhere
        self.set_action_scope('universal')
        self.set_supported_scopes(['universal'])
        
        # Feature type support - universal only, no specific geometry types
        self.set_supported_click_types(['universal'])
        self.set_supported_geometry_types(['universal'])
    
    def get_settings_schema(self):
        """Define the settings schema for this action."""
        return {
            # SCREENSHOT SETTINGS - Easy to customize
            'save_directory': {
                'type': 'directory_path',
                'default': 'C:\\RAT_screenshots',
                'label': 'Save Directory',
                'description': 'Directory where screenshots will be saved. Use ~ for home directory.',
            },
            'filename_template': {
                'type': 'str',
                'default': 'qgis_canvas_screenshot_{timestamp}',
                'label': 'Filename Template',
                'description': 'Template for screenshot filenames. Available variables: {timestamp}, {date}, {time}',
            },
            'file_format': {
                'type': 'choice',
                'default': 'PNG',
                'label': 'File Format',
                'description': 'Image format for screenshots',
                'options': ['PNG', 'JPG', 'BMP', 'TIFF'],
            },
            'image_quality': {
                'type': 'int',
                'default': 95,
                'label': 'Image Quality',
                'description': 'Image quality for JPEG format (1-100)',
                'min': 1,
                'max': 100,
                'step': 1,
            },
            
            # BEHAVIOR SETTINGS - User experience options
            'show_success_message': {
                'type': 'bool',
                'default': False,
                'label': 'Show Success Message',
                'description': 'Display a message when screenshot is saved successfully',
            },
            'auto_open_folder': {
                'type': 'bool',
                'default': False,
                'label': 'Auto-open Folder',
                'description': 'Automatically open the save folder after taking screenshot',
            },
            'include_timestamp_in_filename': {
                'type': 'bool',
                'default': True,
                'label': 'Include Timestamp in Filename',
                'description': 'Automatically add timestamp to filename to prevent overwrites',
            },
            'create_directory_if_missing': {
                'type': 'bool',
                'default': True,
                'label': 'Create Directory if Missing',
                'description': 'Automatically create the save directory if it does not exist',
            },
        }
    
    def execute(self, context):
        """
        Execute the take canvas screenshot action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            save_directory = str(self.get_setting('save_directory', 'C:\\RAT_screenshots'))
            filename_template = str(self.get_setting('filename_template', 'qgis_canvas_screenshot_{timestamp}'))
            file_format = str(self.get_setting('file_format', 'PNG'))
            image_quality = int(self.get_setting('image_quality', 95))
            show_success_message = bool(self.get_setting('show_success_message', False))
            auto_open_folder = bool(self.get_setting('auto_open_folder', False))
            include_timestamp = bool(self.get_setting('include_timestamp_in_filename', True))
            create_directory = bool(self.get_setting('create_directory_if_missing', True))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        canvas = context.get('canvas')
        
        if not canvas:
            return  # Silently fail if no canvas
        
        try:
            # Get save directory
            save_dir = self.get_save_directory(save_directory, create_directory)
            if not save_dir:
                return  # Silently fail if can't get save directory
            
            # Generate filename
            filename = self.generate_filename(filename_template, include_timestamp, file_format)
            filepath = os.path.join(save_dir, filename)
            
            # Take screenshot of the canvas
            pixmap = canvas.grab()
            
            # Save the screenshot
            if pixmap.save(filepath, file_format, image_quality if file_format == 'JPG' else -1):
                # Success
                if show_success_message:
                    self.show_info("Screenshot Saved", f"Screenshot saved to: {filepath}")
                
                if auto_open_folder:
                    self.open_folder(save_dir)
            else:
                # Failed to save - silently handle
                pass
                
        except Exception:
            # Silently handle any errors - no popup windows as requested
            pass
    
    def get_save_directory(self, save_directory, create_if_missing=True):
        """
        Get the save directory path.
        
        Args:
            save_directory (str): Directory path (can include ~ for home)
            create_if_missing (bool): Whether to create directory if it doesn't exist
            
        Returns:
            str: Path to save directory or None if not found
        """
        try:
            # Expand ~ to home directory
            if save_directory.startswith('~'):
                save_path = os.path.expanduser(save_directory)
            else:
                save_path = save_directory
            
            # Normalize the path
            save_path = os.path.normpath(save_path)
            
            # Check if directory exists
            if not os.path.exists(save_path):
                if create_if_missing:
                    # Create directory if it doesn't exist
                    os.makedirs(save_path, exist_ok=True)
                else:
                    # Return None if directory doesn't exist and we shouldn't create it
                    return None
            
            # Verify it's actually a directory
            if not os.path.isdir(save_path):
                return None
            
            return save_path
            
        except Exception:
            # Fallback to current directory if save directory fails
            return os.getcwd()
    
    def generate_filename(self, template, include_timestamp, file_format):
        """
        Generate filename based on template and settings.
        
        Args:
            template (str): Filename template
            include_timestamp (bool): Whether to include timestamp
            file_format (str): File format extension
            
        Returns:
            str: Generated filename
        """
        try:
            # Get current time
            now = datetime.now()
            
            # Replace template variables
            filename = template
            filename = filename.replace('{timestamp}', now.strftime("%Y%m%d_%H%M%S"))
            filename = filename.replace('{date}', now.strftime("%Y%m%d"))
            filename = filename.replace('{time}', now.strftime("%H%M%S"))
            
            # Add timestamp if requested and not already in template
            if include_timestamp and '{timestamp}' not in template and '{date}' not in template:
                timestamp = now.strftime("%Y%m%d_%H%M%S")
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{timestamp}{ext}"
            
            # Ensure proper file extension
            if not filename.lower().endswith(f'.{file_format.lower()}'):
                filename = f"{filename}.{file_format.lower()}"
            
            return filename
            
        except Exception:
            # Fallback to simple timestamped filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return f"qgis_screenshot_{timestamp}.{file_format.lower()}"
    
    def open_folder(self, folder_path):
        """
        Open the specified folder in the system file manager.
        
        Args:
            folder_path (str): Path to folder to open
        """
        try:
            # Normalize the path
            folder_path = os.path.normpath(folder_path)
            
            # Ensure the path is absolute
            if not os.path.isabs(folder_path):
                folder_path = os.path.abspath(folder_path)
            
            # Verify the folder exists
            if not os.path.exists(folder_path):
                return
            
            # Verify it's actually a directory
            if not os.path.isdir(folder_path):
                return
            
            # Open folder based on operating system
            system = platform.system()
            if system == "Windows":
                # Use Windows Explorer
                subprocess.run(["explorer", folder_path], check=False)
            elif system == "Darwin":  # macOS
                # Use Finder
                subprocess.run(["open", folder_path], check=False)
            else:  # Linux and others
                # Use xdg-open
                subprocess.run(["xdg-open", folder_path], check=False)
                
        except Exception:
            # Silently fail if can't open folder
            pass


# REQUIRED: Create global instance for automatic discovery
take_canvas_screenshot_action = TakeCanvasScreenshotAction()