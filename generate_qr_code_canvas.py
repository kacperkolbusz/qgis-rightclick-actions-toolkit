"""
Generate QR Code on Canvas Action for Right-click Utilities and Shortcuts Hub

Generates a QR code at the clicked canvas location. User inputs the text/data to encode,
and the QR code is displayed as a point layer with a picture marker symbol.
"""

from .base_action import BaseAction


class GenerateQrCodeCanvasAction(BaseAction):
    """
    Action to generate a QR code at the clicked canvas location.
    
    This action prompts the user to enter text/data to encode in the QR code,
    then creates a point layer with the QR code displayed as a picture marker.
    """
    
    def __init__(self):
        """Initialize the action with metadata and configuration."""
        super().__init__()
        
        # Required properties
        self.action_id = "generate_qr_code_canvas"
        self.name = "Generate QR Code on Canvas"
        self.category = "Editing"
        self.description = "Generate a QR code at the clicked canvas location. Prompts user to enter text or data to encode, then creates a point layer with the QR code displayed as a picture marker symbol. The QR code can encode URLs, text, coordinates, or any other data."
        self.enabled = True
        
        # Action scoping - works on canvas clicks
        self.set_action_scope('universal')
        self.set_supported_scopes(['universal'])
        
        # Feature type support - works on canvas clicks
        self.set_supported_click_types(['canvas', 'universal'])
        self.set_supported_geometry_types(['canvas', 'universal'])

    def supports_undo(self) -> bool:
        """
        This action supports undo: creating a QR code feature (trivial undo).
        """
        return True

    def get_undo_category(self) -> str:
        """Trivial undo: undo = delete created feature"""
        return 'trivial'
    
    def get_settings_schema(self):
        """
        Define the settings schema for this action.
        
        Returns:
            dict: Settings schema with setting definitions
        """
        return {
            # LAYER SETTINGS
            'layer_name': {
                'type': 'str',
                'default': 'QR Codes',
                'label': 'Layer Name',
                'description': 'Name for the QR code layer. If layer already exists, QR codes will be added to it.',
            },
            'add_to_existing_layer': {
                'type': 'bool',
                'default': True,
                'label': 'Add to Existing Layer',
                'description': 'If a layer with the same name exists, add QR codes to it instead of creating a new layer',
            },
            'layer_storage_type': {
                'type': 'choice',
                'default': 'temporary',
                'label': 'Layer Storage Type',
                'description': 'Temporary layers are in-memory only (lost on QGIS close). Permanent layers are saved to disk.',
                'options': ['temporary', 'permanent'],
            },
            
            # QR CODE SETTINGS
            'qr_code_size': {
                'type': 'int',
                'default': 10,
                'label': 'QR Code Size',
                'description': 'Size of the QR code marker',
                'min': 5,
                'max': 200,
                'step': 1,
            },
            'qr_code_size_unit': {
                'type': 'choice',
                'default': 'MM',
                'label': 'Size Unit',
                'description': 'MM = Fixed screen size (does not change with zoom). Map Units = Scales with map zoom. Pixels = Fixed screen size in pixels.',
                'options': ['MM', 'Map Units', 'Pixels'],
            },
            'qr_code_rotation': {
                'type': 'float',
                'default': 0.0,
                'label': 'Rotation Angle',
                'description': 'Rotation angle in degrees (0-360). Positive values rotate clockwise.',
                'min': 0.0,
                'max': 360.0,
                'step': 1.0,
            },
            'qr_code_opacity': {
                'type': 'int',
                'default': 100,
                'label': 'Opacity (%)',
                'description': 'Opacity of the QR code (0-100). 100 = fully opaque, 0 = fully transparent.',
                'min': 0,
                'max': 100,
                'step': 1,
            },
            'qr_code_error_correction': {
                'type': 'choice',
                'default': 'M',
                'label': 'Error Correction Level',
                'description': 'Higher levels allow QR code to be read even if partially damaged. L=Low (~7%), M=Medium (~15%), Q=Quartile (~25%), H=High (~30%)',
                'options': ['L', 'M', 'Q', 'H'],
            },
            'qr_code_border': {
                'type': 'int',
                'default': 4,
                'label': 'QR Code Border',
                'description': 'Number of border boxes around the QR code (recommended: 4)',
                'min': 1,
                'max': 10,
                'step': 1,
            },
            
            # ATTRIBUTE SETTINGS
            'store_qr_text': {
                'type': 'bool',
                'default': True,
                'label': 'Store QR Code Text',
                'description': 'Store the encoded text in a layer attribute for reference',
            },
            'add_timestamp': {
                'type': 'bool',
                'default': False,
                'label': 'Add Timestamp',
                'description': 'Add timestamp field with creation date and time',
            },
            'add_coordinates': {
                'type': 'bool',
                'default': False,
                'label': 'Add Coordinates',
                'description': 'Add X and Y coordinate fields to the QR code attributes',
            },
            'add_id': {
                'type': 'bool',
                'default': True,
                'label': 'Add ID Field',
                'description': 'Add sequential ID field to each QR code',
            },
            
            # BEHAVIOR SETTINGS
            'auto_zoom': {
                'type': 'bool',
                'default': False,
                'label': 'Auto Zoom to QR Code',
                'description': 'Automatically zoom to the created QR code',
            },
            'show_confirmation': {
                'type': 'bool',
                'default': False,
                'label': 'Show Confirmation',
                'description': 'Show confirmation message when QR code is created',
            },
        }
    
    def get_setting(self, setting_name, default_value=None):
        """
        Get a setting value for this action.
        
        Args:
            setting_name (str): Name of the setting to retrieve
            default_value: Default value if setting not found
            
        Returns:
            Setting value or default_value
        """
        from qgis.PyQt.QtCore import QSettings
        settings = QSettings()
        key = f"RightClickUtilities/{self.action_id}/{setting_name}"
        return settings.value(key, default_value)
    
    def _generate_qr_code_image(self, text, error_correction, border):
        """
        Generate QR code image from text.
        
        Uses qrcode library if available, otherwise falls back to web API.
        
        Args:
            text (str): Text to encode in QR code
            error_correction (str): Error correction level ('L', 'M', 'Q', 'H')
            border (int): Border size in boxes
            
        Returns:
            bytes: PNG image data or None if failed
        """
        # Try using qrcode library first (if available)
        try:
            import qrcode
            from io import BytesIO
            
            # Map error correction level
            error_correction_map = {
                'L': qrcode.constants.ERROR_CORRECT_L,
                'M': qrcode.constants.ERROR_CORRECT_M,
                'Q': qrcode.constants.ERROR_CORRECT_Q,
                'H': qrcode.constants.ERROR_CORRECT_H,
            }
            error_level = error_correction_map.get(error_correction, qrcode.constants.ERROR_CORRECT_M)
            
            # Create QR code instance
            qr = qrcode.QRCode(
                version=1,
                error_correction=error_level,
                box_size=10,
                border=border,
            )
            
            # Add data
            qr.add_data(text)
            qr.make(fit=True)
            
            # Create image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to bytes
            img_bytes = BytesIO()
            img.save(img_bytes, format='PNG')
            img_bytes.seek(0)
            
            return img_bytes.getvalue()
            
        except ImportError:
            # Fall back to web API (no dependencies required)
            return self._generate_qr_code_via_web_api(text, error_correction, border)
        except Exception as e:
            # If qrcode fails, try web API as fallback
            print(f"QR code library error: {str(e)}, trying web API fallback...")
            return self._generate_qr_code_via_web_api(text, error_correction, border)
    
    def _generate_qr_code_via_web_api(self, text, error_correction, border):
        """
        Generate QR code using web API (no dependencies required).
        
        Uses free QR code API services that work with standard library only.
        
        Args:
            text (str): Text to encode in QR code
            error_correction (str): Error correction level ('L', 'M', 'Q', 'H')
            border (int): Border size in boxes (not all APIs support this)
            
        Returns:
            bytes: PNG image data or None if failed
        """
        try:
            from urllib.parse import quote
            from urllib.request import urlopen, Request
            import io
            
            # Use api.qrserver.com - free, no API key required
            # URL format: https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=text
            encoded_text = quote(text)
            
            # Map error correction to API parameter (if supported)
            # api.qrserver.com uses ECC level: L, M, Q, H
            ecc_level = error_correction.upper()
            
            # Build API URL
            # Size: 300x300 pixels (adjustable, but we'll use fixed size and scale in QGIS)
            size = 300  # Base size, will be scaled by QGIS marker size
            api_url = f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&ecc={ecc_level}&data={encoded_text}"
            
            # Validate API URL scheme to prevent unexpected schemes (file:, custom, etc.)
            try:
                from urllib.parse import urlparse
                parsed = urlparse(api_url)
                if (parsed.scheme or '').lower() not in ('http', 'https'):
                    raise ValueError(f"Disallowed URL scheme: {parsed.scheme}")
            except Exception as e:
                print(f"Invalid API URL scheme: {str(e)}")
                # Let outer exception handler try alternative API
                raise

            request = Request(api_url)
            request.add_header('User-Agent', 'QGIS-RightClickUtilities/1.0')

            with urlopen(request, timeout=10) as response:
                image_data = response.read()
            
            # Verify it's actually an image
            if image_data.startswith(b"\x89PNG") or image_data.startswith(b"\xff\xd8"):
                return image_data
            else:
                # Try alternative API
                return self._generate_qr_code_via_alternative_api(text)
        except Exception as e:
            # Try alternative API if first one fails
            print(f"Primary QR code API failed: {str(e)}, trying alternative...")
            return self._generate_qr_code_via_alternative_api(text)

    def _is_allowed_url_scheme(self, url):
        """
        Return True if URL has an allowed scheme (http or https), False otherwise.
        """
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            return (parsed.scheme or '').lower() in ('http', 'https')
        except Exception:
            return False
    
    def _generate_qr_code_via_alternative_api(self, text):
        """
        Generate QR code using alternative web API.
        
        Args:
            text (str): Text to encode in QR code
            
        Returns:
            bytes: PNG image data or None if failed
        """
        try:
            from urllib.parse import quote
            from urllib.request import urlopen, Request
            
            # Use qr-code-generator.com API as fallback
            encoded_text = quote(text)
            api_url = f"https://api.qr-code-generator.com/v1/create/qr-code?size=300&data={encoded_text}"
            
            # Validate API URL scheme before making request
            if not self._is_allowed_url_scheme(api_url):
                raise ValueError(f"Disallowed URL scheme: {api_url}")

            request = Request(api_url)
            request.add_header('User-Agent', 'QGIS-RightClickUtilities/1.0')

            with urlopen(request, timeout=10) as response:
                image_data = response.read()
            
            if image_data and len(image_data) > 100:  # Basic validation
                return image_data
            else:
                raise Exception("Invalid image data received")
                
        except Exception as e:
            self.show_error("Error", f"Failed to generate QR code via web API: {str(e)}\n\nPlease check your internet connection or install 'qrcode' library:\npip install qrcode[pil]")
            return None
    
    def _save_qr_code_to_temp(self, qr_image_data, qr_id):
        """
        Save QR code image to temporary file.
        
        Args:
            qr_image_data (bytes): PNG image data
            qr_id (int): Unique ID for the QR code
            
        Returns:
            str: Path to saved file or None if failed
        """
        try:
            import tempfile
            import os
            
            # Create temp directory if it doesn't exist
            temp_dir = os.path.join(tempfile.gettempdir(), 'qgis_qr_codes')
            os.makedirs(temp_dir, exist_ok=True)
            
            # Save QR code image
            file_path = os.path.join(temp_dir, f'qr_code_{qr_id}.png')
            with open(file_path, 'wb') as f:
                f.write(qr_image_data)
            
            # Verify file was created and has content
            if not os.path.exists(file_path):
                raise Exception(f"File was not created: {file_path}")
            
            file_size = os.path.getsize(file_path)
            if file_size == 0:
                raise Exception(f"File is empty: {file_path}")
            
            return file_path
            
        except Exception as e:
            self.show_error("Error", f"Failed to save QR code image: {str(e)}")
            return None
    
    def _apply_qr_code_symbol(self, layer, qr_image_path, symbol_settings):
        """
        Apply QR code image as picture marker symbol to layer.
        
        Args:
            layer (QgsVectorLayer): Layer to style
            qr_image_path (str): Path to QR code image file
            symbol_settings (dict): Dictionary with size, size_unit, rotation, opacity
        """
        qr_code_size = symbol_settings.get('size', 10)
        qr_code_size_unit = symbol_settings.get('size_unit', 'MM')
        qr_code_rotation = symbol_settings.get('rotation', 0.0)
        qr_code_opacity = symbol_settings.get('opacity', 100)
        try:
            import os
            from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer
            
            # Verify file exists
            if not os.path.exists(qr_image_path):
                error_msg = f"QR code image file not found: {qr_image_path}"
                print(f"Warning: {error_msg}")
                self.show_warning("QR Code Symbol", error_msg)
                return
            
            # Convert to absolute path and normalize
            abs_path = os.path.abspath(qr_image_path)
            abs_path = abs_path.replace('\\', '/')  # Use forward slashes for QGIS
            
            # Try multiple approaches to apply QR code symbol
            success = False
            
            # Approach 1: Try QgsRasterMarkerSymbolLayer directly
            try:
                from qgis.core import QgsRasterMarkerSymbolLayer
                
                # Create raster marker symbol layer with QR code image
                symbol_layer = QgsRasterMarkerSymbolLayer(abs_path)
                
                # Set size
                symbol_layer.setSize(qr_code_size)
                
                # Set size unit based on setting (MM = fixed screen size, Map Units = scales with zoom)
                try:
                    from qgis.core import QgsUnitTypes
                    if qr_code_size_unit == 'MM':
                        symbol_layer.setSizeUnit(QgsUnitTypes.RenderMillimeters)  # Fixed screen size
                    elif qr_code_size_unit == 'Pixels':
                        symbol_layer.setSizeUnit(QgsUnitTypes.RenderPixels)  # Fixed screen size
                    else:  # Map Units
                        symbol_layer.setSizeUnit(QgsUnitTypes.RenderMapUnits)  # Scales with zoom
                except:
                    # Fallback to numeric constants: 1=MM, 0=Pixel, 2=MapUnit
                    if qr_code_size_unit == 'MM':
                        symbol_layer.setSizeUnit(1)  # Millimeters - fixed screen size
                    elif qr_code_size_unit == 'Pixels':
                        symbol_layer.setSizeUnit(0)  # Pixels - fixed screen size
                    else:  # Map Units
                        symbol_layer.setSizeUnit(2)  # Map units - scales with zoom
                
                # Set rotation
                if qr_code_rotation != 0.0:
                    try:
                        symbol_layer.setAngle(qr_code_rotation)
                    except:
                        try:
                            symbol_layer.setAngle(qr_code_rotation)
                        except:
                            pass  # Rotation not supported in this version
                
                # Set opacity (alpha)
                if qr_code_opacity < 100:
                    alpha = qr_code_opacity / 100.0
                    try:
                        symbol_layer.setAlpha(alpha)
                    except:
                        try:
                            symbol_layer.setOpacity(alpha)
                        except:
                            pass  # Opacity not supported in this version
                
                # Create marker symbol
                symbol = QgsMarkerSymbol()
                symbol.changeSymbolLayer(0, symbol_layer)
                
                # Apply symbol to layer
                renderer = QgsSingleSymbolRenderer(symbol)
                layer.setRenderer(renderer)
                layer.triggerRepaint()
                success = True
                print(f"Successfully applied QR code symbol using RasterMarkerSymbolLayer")
                return  # Success, exit early
                
            except (ImportError, AttributeError, Exception) as e1:
                print(f"RasterMarkerSymbolLayer approach failed: {str(e1)}")
                import traceback
                traceback.print_exc()
                
                # Approach 2: Try creating via symbol registry
                try:
                    from qgis.core import QgsSymbolLayerRegistry
                    
                    registry = QgsSymbolLayerRegistry.instance()
                    metadata = registry.symbolLayerMetadata("RasterMarker")
                    if metadata:
                        # Map size unit to QGIS format
                        size_unit_str = 'MM' if qr_code_size_unit == 'MM' else ('Pixel' if qr_code_size_unit == 'Pixels' else 'MapUnit')
                        props = {
                            'imageFile': abs_path,
                            'size': str(qr_code_size),
                            'size_unit': size_unit_str
                        }
                        if qr_code_rotation != 0.0:
                            props['angle'] = str(qr_code_rotation)
                        if qr_code_opacity < 100:
                            props['alpha'] = str(qr_code_opacity / 100.0)
                        symbol_layer = metadata.createSymbolLayer(props)
                        if symbol_layer:
                            symbol = QgsMarkerSymbol()
                            symbol.deleteSymbolLayer(0)
                            symbol.appendSymbolLayer(symbol_layer)
                            renderer = QgsSingleSymbolRenderer(symbol)
                            layer.setRenderer(renderer)
                            layer.triggerRepaint()
                            success = True
                            print(f"Successfully applied QR code symbol using registry")
                except Exception as e2:
                    print(f"Registry approach failed: {str(e2)}")
                    import traceback
                    traceback.print_exc()
            
            # Approach 3: Try using style manager with QML/XML
            if not success:
                try:
                    success = self._apply_qr_code_via_style_manager(layer, abs_path, symbol_settings)
                    if success:
                        print("Successfully applied QR code via style manager")
                        return
                except Exception as e3:
                    print(f"Style manager approach failed: {str(e3)}")
            
            # Approach 4: Try creating symbol from properties map
            if not success:
                try:
                    success = self._apply_qr_code_via_properties_map(layer, abs_path, symbol_settings)
                    if success:
                        print("Successfully applied QR code via properties map")
                        return
                except Exception as e4:
                    print(f"Properties map approach failed: {str(e4)}")
            
            # Approach 5: Last resort - show instructions
            if not success:
                self._apply_qr_code_as_raster_overlay(layer, abs_path, symbol_settings)
            
        except Exception as e:
            # If styling fails, show error but continue
            error_msg = f"Could not apply QR code symbol: {str(e)}"
            print(f"Warning: {error_msg}")
            import traceback
            traceback.print_exc()
            # Try to show in QGIS message bar if possible
            try:
                self.show_warning("QR Code Symbol", error_msg)
            except:
                pass
    
    def _create_polygon_qr_code_visualization(self, layer, qr_image_path, qr_code_size):
        """
        Unconventional approach: Create a square polygon around each point
        and style it to represent the QR code area.
        
        This creates a visible square that users can see, and we store
        the QR code image path for manual styling.
        
        Args:
            layer (QgsVectorLayer): Point layer
            qr_image_path (str): Path to QR code image
            qr_code_size (int): Size in millimeters
            
        Returns:
            bool: True if successful
        """
        try:
            from qgis.core import QgsGeometry, QgsRectangle, QgsPointXY
            from qgis.PyQt.QtGui import QColor
            from qgis.core import QgsSimpleFillSymbolLayer, QgsSimpleLineSymbolLayer
            
            # Get canvas to calculate size in map units
            canvas = None
            try:
                from qgis.core import QgsProject
                project = QgsProject.instance()
                # Try to get canvas from context if available
                # For now, use a default size calculation
                canvas = None
            except:
                pass
            
            # Calculate size in map units (approximate)
            # Default: assume 1mm = ~0.001 map units at typical scales
            # This is a rough approximation
            size_map_units = qr_code_size * 0.001  # Rough conversion
            
            # Create a square polygon around each point
            features = list(layer.getFeatures())
            if not features:
                return False
            
            # Store QR code info in layer metadata
            layer.setCustomProperty("qr_code_image", qr_image_path)
            layer.setCustomProperty("qr_code_size", str(qr_code_size))
            
            # Style the points as visible squares to indicate QR code location
            symbol = QgsMarkerSymbol.createSimple({
                'name': 'square',
                'color': '0,0,0,255',  # Black
                'outline_color': '255,255,255,255',  # White outline
                'size': str(qr_code_size * 0.5),  # Smaller visible marker
                'size_unit': 'MM'
            })
            
            renderer = QgsSingleSymbolRenderer(symbol)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
            
            # Show helpful message
            self.show_info(
                "QR Code Created", 
                f"QR code point created with visible marker!\n\n"
                f"The QR code image is saved and ready to use.\n\n"
                f"To display the QR code image:\n"
                f"1. Right-click layer → Properties → Symbology\n"
                f"2. Change symbol to 'Raster Image Marker'\n"
                f"3. Browse to: {qr_image_path}\n"
                f"4. Set size to {qr_code_size} mm\n\n"
                f"Image location:\n{qr_image_path}"
            )
            
            return True
            
        except Exception as e:
            print(f"Polygon visualization approach failed: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def _apply_qr_code_via_style_manager(self, layer, qr_image_path, symbol_settings):
        """
        Try to apply QR code using QGIS style manager.
        
        Args:
            layer (QgsVectorLayer): Layer to style
            qr_image_path (str): Path to QR code image
            symbol_settings (dict): Dictionary with size, size_unit, rotation, opacity
            
        Returns:
            bool: True if successful
        """
        try:
            from qgis.core import QgsReadWriteContext, QgsMarkerSymbol
            from qgis.PyQt.QtXml import QDomDocument, QDomElement
            from qgis.core import QgsSingleSymbolRenderer
            
            qr_code_size = symbol_settings.get('size', 10)
            qr_code_size_unit = symbol_settings.get('size_unit', 'MM')
            qr_code_rotation = symbol_settings.get('rotation', 0.0)
            qr_code_opacity = symbol_settings.get('opacity', 100)
            
            # Create QML style XML
            escaped_path = qr_image_path.replace('\\', '/').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
            
            # Map size unit
            size_unit_str = 'MM' if qr_code_size_unit == 'MM' else ('Pixel' if qr_code_size_unit == 'Pixels' else 'MapUnit')
            alpha_val = qr_code_opacity / 100.0
            
            qml_xml = f'''<!DOCTYPE qgis PUBLIC 'http://mrcc.com/qgis.dtd' 'SYSTEM'>
<qgis version="3.0" simplifyDrawingHints="0" simplifyMaxScale="1" simplifyAlgorithm="0" simplifyLocal="1" readOnly="0" hasScaleBasedVisibilityFlag="0" styleCategories="AllStyleCategories">
  <renderer-v2 symbollevels="0" type="singleSymbol" forceraster="0" enableorderby="0">
    <symbols>
      <symbol alpha="{alpha_val}" clip_to_extent="1" type="marker" name="qr_code">
        <layer class="RasterMarker" locked="0" pass="0" enabled="1">
          <prop k="alpha" v="{alpha_val}"/>
          <prop k="angle" v="{qr_code_rotation}"/>
          <prop k="fixedAspectRatio" v="0"/>
          <prop k="horizontal_anchor_point" v="1"/>
          <prop k="imageFile" v="{escaped_path}"/>
          <prop k="offset" v="0,0"/>
          <prop k="offset_map_unit_scale" v="3x:0,0,0,0,0,0"/>
          <prop k="offset_unit" v="MM"/>
          <prop k="size" v="{qr_code_size}"/>
          <prop k="size_map_unit_scale" v="3x:0,0,0,0,0,0"/>
          <prop k="size_unit" v="{size_unit_str}"/>
          <prop k="vertical_anchor_point" v="1"/>
        </layer>
      </symbol>
    </symbols>
  </renderer-v2>
</qgis>'''
            
            # Try to import style
            doc = QDomDocument()
            if doc.setContent(qml_xml):
                context = QgsReadWriteContext()
                # Try to read the renderer from XML
                element = doc.documentElement()
                renderer_elem = element.firstChildElement("renderer-v2")
                if not renderer_elem.isNull():
                    # Create renderer from XML
                    from qgis.core import QgsFeatureRenderer
                    renderer = QgsFeatureRenderer.load(renderer_elem, context)
                    if renderer:
                        layer.setRenderer(renderer)
                        layer.triggerRepaint()
                        return True
            
            return False
            
        except Exception as e:
            print(f"Style manager approach error: {str(e)}")
            return False
    
    def _apply_qr_code_via_properties_map(self, layer, qr_image_path, symbol_settings):
        """
        Try to create symbol layer using properties map directly.
        
        Args:
            layer (QgsVectorLayer): Layer to style
            qr_image_path (str): Path to QR code image
            symbol_settings (dict): Dictionary with size, size_unit, rotation, opacity
            
        Returns:
            bool: True if successful
        """
        try:
            from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer
            
            qr_code_size = symbol_settings.get('size', 10)
            qr_code_size_unit = symbol_settings.get('size_unit', 'MM')
            qr_code_rotation = symbol_settings.get('rotation', 0.0)
            qr_code_opacity = symbol_settings.get('opacity', 100)
            
            # Try to create symbol using default and modify
            symbol = QgsMarkerSymbol.createSimple({})
            
            # Try to replace symbol layer with raster marker
            # This is a workaround - create a new symbol with raster layer
            try:
                # Get the symbol layer registry - try multiple ways
                registry = None
                try:
                    from qgis.core import QgsApplication
                    registry = QgsApplication.symbolLayerRegistry()
                except:
                    try:
                        from qgis.core import QgsSymbolLayerRegistry
                        registry = QgsSymbolLayerRegistry.instance()
                    except:
                        pass
                
                if registry:
                    metadata = registry.symbolLayerMetadata("RasterMarker")
                    
                    if metadata:
                        # Map size unit
                        size_unit_str = 'MM' if qr_code_size_unit == 'MM' else ('Pixel' if qr_code_size_unit == 'Pixels' else 'MapUnit')
                        
                        # Create properties map
                        props = {
                            'imageFile': qr_image_path,
                            'size': str(qr_code_size),
                            'size_unit': size_unit_str,
                            'alpha': str(qr_code_opacity / 100.0),
                            'angle': str(qr_code_rotation)
                        }
                    
                    # Create symbol layer
                    symbol_layer = metadata.createSymbolLayer(props)
                    if symbol_layer:
                        # Replace in symbol
                        symbol.deleteSymbolLayer(0)
                        symbol.appendSymbolLayer(symbol_layer)
                        
                        # Apply
                        renderer = QgsSingleSymbolRenderer(symbol)
                        layer.setRenderer(renderer)
                        layer.triggerRepaint()
                        return True
            except Exception as e:
                print(f"Properties map creation failed: {str(e)}")
            
            return False
            
        except Exception as e:
            print(f"Properties map approach error: {str(e)}")
            return False
    
    def _apply_qr_code_as_raster_overlay(self, layer, qr_image_path, symbol_settings):
        """
        Alternative approach: Store QR code info and provide instructions.
        
        Args:
            layer (QgsVectorLayer): Point layer
            qr_image_path (str): Path to QR code image
            symbol_settings (dict): Dictionary with size, size_unit, rotation, opacity
            
        Returns:
            bool: True if successful
        """
        try:
            qr_code_size = symbol_settings.get('size', 10)
            qr_code_size_unit = symbol_settings.get('size_unit', 'MM')
            
            # Store the image path in layer metadata
            layer.setCustomProperty("qr_code_image", qr_image_path)
            layer.setCustomProperty("qr_code_size", str(qr_code_size))
            layer.setCustomProperty("qr_code_size_unit", qr_code_size_unit)
            
            # Show message to user about manual setup
            self.show_info(
                "QR Code Created", 
                f"QR code point created successfully!\n\n"
                f"To display the QR code image:\n"
                f"1. Right-click the layer → Properties → Symbology\n"
                f"2. Change symbol type to 'Raster Image Marker'\n"
                f"3. Browse to: {qr_image_path}\n"
                f"4. Set size to {qr_code_size} {qr_code_size_unit.lower()}\n\n"
                f"Image saved at:\n{qr_image_path}"
            )
            return True
            
        except Exception as e:
            print(f"Raster overlay approach failed: {str(e)}")
            return False
    
    def _apply_qr_code_symbol_via_xml(self, layer, qr_image_path, qr_code_size):
        """
        Apply QR code symbol using XML style definition (fallback method).
        
        Args:
            layer (QgsVectorLayer): Layer to style
            qr_image_path (str): Absolute path to QR code image file
            qr_code_size (int): Size of marker in millimeters
        """
        try:
            from qgis.core import QgsMarkerSymbol, QgsSingleSymbolRenderer, QgsReadWriteContext
            from qgis.PyQt.QtCore import QFileInfo, QDomDocument, QDomElement
            from qgis.PyQt.QtXml import QDomDocument
            
            # Escape path for XML
            escaped_path = qr_image_path.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
            
            # Create style XML for raster marker (QGIS style format)
            style_xml = f'''<symbol alpha="1" clip_to_extent="1" type="marker" name="qr_code">
    <layer class="RasterMarker" locked="0" pass="0" enabled="1">
        <prop k="alpha" v="1"/>
        <prop k="angle" v="0"/>
        <prop k="fixedAspectRatio" v="0"/>
        <prop k="horizontal_anchor_point" v="1"/>
        <prop k="imageFile" v="{escaped_path}"/>
        <prop k="offset" v="0,0"/>
        <prop k="offset_map_unit_scale" v="3x:0,0,0,0,0,0"/>
        <prop k="offset_unit" v="MM"/>
        <prop k="size" v="{qr_code_size}"/>
        <prop k="size_map_unit_scale" v="3x:0,0,0,0,0,0"/>
        <prop k="size_unit" v="MM"/>
        <prop k="vertical_anchor_point" v="1"/>
    </layer>
</symbol>'''
            
            # Parse XML and create symbol
            doc = QDomDocument()
            if doc.setContent(style_xml):
                element = doc.documentElement()
                context = QgsReadWriteContext()
                symbol = QgsMarkerSymbol.createFromSld(element, context)
                
                if symbol is None or symbol.symbolLayerCount() == 0:
                    # Try alternative: create default and set properties via style
                    symbol = QgsMarkerSymbol.createSimple({})
                    print("Warning: Could not create symbol from XML, using default marker")
                    print("Note: QR code image saved at:", qr_image_path)
                    print("You can manually set the layer style to use this image file.")
            else:
                symbol = QgsMarkerSymbol.createSimple({})
                print("Warning: Could not parse XML, using default marker")
            
            # Apply symbol to layer
            renderer = QgsSingleSymbolRenderer(symbol)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
            
        except Exception as e:
            print(f"Warning: XML symbol application failed: {str(e)}")
            import traceback
            traceback.print_exc()
            # Continue with default symbol - at least the point will be visible
            # User can manually set the style to use the QR code image
    
    def _create_qr_code_layer(self, layer_name, point, crs, qr_text, qr_image_path, symbol_settings, settings):
        """
        Create a new point layer with QR code feature.
        
        Args:
            layer_name (str): Name for the layer
            point (QgsPointXY): Point location
            crs: Coordinate reference system
            qr_text (str): Text encoded in QR code
            qr_image_path (str): Path to QR code image
            qr_code_size (int): Size of QR code marker
            settings (dict): Settings dictionary
            
        Returns:
            QgsVectorLayer: Created layer or None if failed
        """
        try:
            from qgis.core import QgsVectorLayer, QgsFields, QgsField, QgsFeature, QgsGeometry, QgsProject
            from qgis.PyQt.QtCore import QVariant
            
            # Create memory layer
            crs_string = crs.authid() if crs.authid() else crs.toWkt()
            layer = QgsVectorLayer(f"Point?crs={crs_string}", layer_name, "memory")
            
            if not layer.isValid():
                self.show_error("Error", f"Failed to create valid temporary layer. CRS: {crs_string}")
                return None
            
            # Define fields
            fields = QgsFields()
            
            if settings['add_id']:
                fields.append(QgsField('id', QVariant.Int, 'integer'))
            
            if settings['store_qr_text']:
                fields.append(QgsField('qr_text', QVariant.String, 'string'))
            
            if settings['add_coordinates']:
                fields.append(QgsField('x', QVariant.Double, 'double'))
                fields.append(QgsField('y', QVariant.Double, 'double'))
            
            if settings['add_timestamp']:
                fields.append(QgsField('created_at', QVariant.String, 'string'))
            
            if fields.count() > 0:
                layer.dataProvider().addAttributes(fields.toList())
                layer.updateFields()
            
            # Create point feature
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromPointXY(point))
            
            # Set attributes
            attributes = []
            if settings['add_id']:
                attributes.append(1)  # First QR code gets ID 1
            
            if settings['store_qr_text']:
                attributes.append(qr_text)
            
            if settings['add_coordinates']:
                attributes.append(float(point.x()))
                attributes.append(float(point.y()))
            
            if settings['add_timestamp']:
                from datetime import datetime
                attributes.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
            
            feature.setAttributes(attributes)
            
            # Add feature to layer
            layer.dataProvider().addFeature(feature)
            layer.updateExtents()
            
            # Apply QR code symbol
            self._apply_qr_code_symbol(layer, qr_image_path, symbol_settings)
            
            return layer
            
        except Exception as e:
            self.show_error("Error", f"Failed to create QR code layer: {str(e)}")
            return None
    
    def _add_qr_code_to_layer(self, layer, point, crs, qr_text, qr_image_path, symbol_settings, settings):
        """
        Add a QR code to an existing layer.
        
        Args:
            layer (QgsVectorLayer): Existing layer to add QR code to
            point (QgsPointXY): Point location
            crs: Coordinate reference system
            qr_text (str): Text encoded in QR code
            qr_image_path (str): Path to QR code image
            qr_code_size (int): Size of QR code marker
            settings (dict): Settings dictionary
        """
        try:
            from qgis.core import QgsFeature, QgsGeometry, QgsField, QgsCoordinateTransform, QgsProject
            from qgis.PyQt.QtCore import QVariant
            
            # Transform point if CRS differs
            if layer.crs() != crs:
                transform = QgsCoordinateTransform(crs, layer.crs(), QgsProject.instance())
                try:
                    point = transform.transform(point)
                except Exception as e:
                    self.show_error("Error", f"CRS transformation failed: {str(e)}")
                    return
            
            # Get field indices
            field_indices = {}
            fields = layer.fields()
            
            if settings['add_id']:
                id_field_idx = fields.indexOf('id')
                if id_field_idx == -1:
                    layer.dataProvider().addAttributes([QgsField('id', QVariant.Int, 'integer')])
                    layer.updateFields()
                    id_field_idx = layer.fields().indexOf('id')
                field_indices['id'] = id_field_idx
            
            if settings['store_qr_text']:
                qr_text_field_idx = fields.indexOf('qr_text')
                if qr_text_field_idx == -1:
                    layer.dataProvider().addAttributes([QgsField('qr_text', QVariant.String, 'string')])
                    layer.updateFields()
                    qr_text_field_idx = layer.fields().indexOf('qr_text')
                field_indices['qr_text'] = qr_text_field_idx
            
            if settings['add_coordinates']:
                x_field_idx = fields.indexOf('x')
                y_field_idx = fields.indexOf('y')
                if x_field_idx == -1 or y_field_idx == -1:
                    layer.dataProvider().addAttributes([
                        QgsField('x', QVariant.Double, 'double'),
                        QgsField('y', QVariant.Double, 'double')
                    ])
                    layer.updateFields()
                    x_field_idx = layer.fields().indexOf('x')
                    y_field_idx = layer.fields().indexOf('y')
                field_indices['x'] = x_field_idx
                field_indices['y'] = y_field_idx
            
            if settings['add_timestamp']:
                timestamp_field_idx = fields.indexOf('created_at')
                if timestamp_field_idx == -1:
                    layer.dataProvider().addAttributes([QgsField('created_at', QVariant.String, 'string')])
                    layer.updateFields()
                    timestamp_field_idx = layer.fields().indexOf('created_at')
                field_indices['timestamp'] = timestamp_field_idx
            
            # Get next ID
            next_id = 1
            if settings['add_id'] and 'id' in field_indices:
                max_id = 0
                for feature in layer.getFeatures():
                    attrs = feature.attributes()
                    if field_indices['id'] < len(attrs):
                        try:
                            feature_id = int(attrs[field_indices['id']])
                            if feature_id > max_id:
                                max_id = feature_id
                        except:
                            pass
                next_id = max_id + 1
            
            # Create feature
            feature = QgsFeature()
            feature.setGeometry(QgsGeometry.fromPointXY(point))
            
            # Set attributes
            attributes = [None] * len(layer.fields())
            
            if settings['add_id'] and 'id' in field_indices:
                attributes[field_indices['id']] = next_id
            
            if settings['store_qr_text'] and 'qr_text' in field_indices:
                attributes[field_indices['qr_text']] = qr_text
            
            if settings['add_coordinates']:
                if 'x' in field_indices:
                    attributes[field_indices['x']] = float(point.x())
                if 'y' in field_indices:
                    attributes[field_indices['y']] = float(point.y())
            
            if settings['add_timestamp'] and 'timestamp' in field_indices:
                from datetime import datetime
                attributes[field_indices['timestamp']] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            feature.setAttributes(attributes)
            
            # Add feature to layer and get created feature id
            success, added_features = layer.dataProvider().addFeatures([feature])
            layer.updateExtents()
            created_fid = None
            if success and added_features:
                try:
                    created_fid = added_features[0].id()
                except Exception:
                    created_fid = None

            # Apply QR code symbol (update styling for all features)
            self._apply_qr_code_symbol(layer, qr_image_path, symbol_settings)

            return created_fid
            
        except Exception as e:
            self.show_error("Error", f"Failed to add QR code to layer: {str(e)}")
            return None
    
    def execute(self, context):
        """
        Execute the generate QR code action.
        
        Args:
            context (dict): Context dictionary with click information
        """
        # Get settings with proper type conversion
        try:
            layer_name = str(self.get_setting('layer_name', 'QR Codes'))
            add_to_existing_layer = bool(self.get_setting('add_to_existing_layer', True))
            layer_storage_type = str(self.get_setting('layer_storage_type', 'temporary'))
            qr_code_size = int(self.get_setting('qr_code_size', 10))
            qr_code_size_unit = str(self.get_setting('qr_code_size_unit', 'MM'))
            qr_code_rotation = float(self.get_setting('qr_code_rotation', 0.0))
            qr_code_opacity = int(self.get_setting('qr_code_opacity', 100))
            qr_code_error_correction = str(self.get_setting('qr_code_error_correction', 'M'))
            qr_code_border = int(self.get_setting('qr_code_border', 4))
            store_qr_text = bool(self.get_setting('store_qr_text', True))
            add_timestamp = bool(self.get_setting('add_timestamp', False))
            add_coordinates = bool(self.get_setting('add_coordinates', False))
            add_id = bool(self.get_setting('add_id', True))
            auto_zoom = bool(self.get_setting('auto_zoom', False))
            show_confirmation = bool(self.get_setting('show_confirmation', False))
        except (ValueError, TypeError) as e:
            self.show_error("Error", f"Invalid setting values: {str(e)}")
            return
        
        # Extract context elements
        click_point = context.get('click_point')
        canvas = context.get('canvas')
        
        if not click_point:
            self.show_error("Error", "No click point available")
            return
        
        if not canvas:
            self.show_error("Error", "Map canvas not available")
            return
        
        # Prompt user for QR code text
        from qgis.PyQt.QtWidgets import QInputDialog
        
        qr_text, ok = QInputDialog.getText(
            None,
            "Generate QR Code",
            "Enter text or data to encode in QR code:"
        )
        
        if not ok or not qr_text.strip():
            return  # User cancelled or entered empty text
        
        qr_text = qr_text.strip()
        
        try:
            # Generate QR code image
            qr_image_data = self._generate_qr_code_image(qr_text, qr_code_error_correction, qr_code_border)
            if not qr_image_data:
                return  # Error already shown
            
            # Get canvas CRS
            canvas_crs = canvas.mapSettings().destinationCrs()
            
            # Generate unique ID for QR code
            import time
            qr_id = int(time.time() * 1000)  # Use timestamp as unique ID
            
            # Save QR code to temp file
            qr_image_path = self._save_qr_code_to_temp(qr_image_data, qr_id)
            if not qr_image_path:
                return  # Error already shown
            
            # Prepare symbol settings
            symbol_settings = {
                'size': qr_code_size,
                'size_unit': qr_code_size_unit,
                'rotation': qr_code_rotation,
                'opacity': qr_code_opacity,
            }
            
            # Check if layer already exists
            existing_layer = None
            if add_to_existing_layer:
                from qgis.core import QgsProject
                project = QgsProject.instance()
                layers = project.mapLayersByName(layer_name)
                for layer in layers:
                    if layer.geometryType() == 0:  # Point layer
                        existing_layer = layer
                        break
            
            settings_dict = {
                'add_timestamp': add_timestamp,
                'add_coordinates': add_coordinates,
                'add_id': add_id,
                'store_qr_text': store_qr_text,
            }
            
            if existing_layer:
                # Add QR code to existing layer
                created_fid = self._add_qr_code_to_layer(
                    existing_layer, click_point, canvas_crs, qr_text, qr_image_path, symbol_settings, settings_dict
                )

                # Trigger repaint
                existing_layer.triggerRepaint()

                # Record history if feature was created
                if created_fid is not None:
                    try:
                        from qgis.core import QgsFeatureRequest
                        created_feature = None
                        for f in existing_layer.getFeatures(QgsFeatureRequest().setFilterFid(created_fid)):
                            created_feature = f
                            break

                        feature_backup = self.create_feature_backup(created_feature, existing_layer) if created_feature else {'fid': created_fid}

                        self.record_to_history(
                            description=f"Created QR code in layer '{existing_layer.name()}'",
                            undo_type='create_feature',
                            can_undo=True,
                            layers=[self.create_layer_descriptor(existing_layer)],
                            features=[feature_backup],
                            meta={'layer_was_created': False}
                        )
                    except Exception:
                        pass

                if show_confirmation:
                    self.show_info("QR Code Added", f"QR code added to existing layer '{layer_name}'")
            else:
                # Create new layer
                if layer_storage_type == 'permanent':
                    # Prompt user for save location
                    from qgis.PyQt.QtWidgets import QFileDialog
                    save_path, _ = QFileDialog.getSaveFileName(
                        None, "Save QR Code Layer As", "", "GeoPackage (*.gpkg);;Shapefile (*.shp)"
                    )
                    if not save_path:
                        return  # User cancelled
                    
                    # Create permanent layer
                    from qgis.core import QgsVectorFileWriter, QgsVectorLayer, QgsFields, QgsField, QgsFeature, QgsGeometry, QgsProject
                    from qgis.PyQt.QtCore import QVariant
                    
                    crs_string = canvas_crs.authid() if canvas_crs.authid() else canvas_crs.toWkt()
                    layer = QgsVectorLayer(f"Point?crs={crs_string}", layer_name, "memory")
                    
                    if not layer.isValid():
                        self.show_error("Error", "Failed to create layer")
                        return
                    
                    # Define fields (same as temporary layer)
                    fields = QgsFields()
                    if settings_dict['add_id']:
                        fields.append(QgsField('id', QVariant.Int, 'integer'))
                    if settings_dict['store_qr_text']:
                        fields.append(QgsField('qr_text', QVariant.String, 'string'))
                    if settings_dict['add_coordinates']:
                        fields.append(QgsField('x', QVariant.Double, 'double'))
                        fields.append(QgsField('y', QVariant.Double, 'double'))
                    if settings_dict['add_timestamp']:
                        fields.append(QgsField('created_at', QVariant.String, 'string'))
                    
                    if fields.count() > 0:
                        layer.dataProvider().addAttributes(fields.toList())
                        layer.updateFields()
                    
                    # Add feature
                    feature = QgsFeature()
                    feature.setGeometry(QgsGeometry.fromPointXY(click_point))
                    attributes = []
                    if settings_dict['add_id']:
                        attributes.append(1)
                    if settings_dict['store_qr_text']:
                        attributes.append(qr_text)
                    if settings_dict['add_coordinates']:
                        attributes.append(float(click_point.x()))
                        attributes.append(float(click_point.y()))
                    if settings_dict['add_timestamp']:
                        from datetime import datetime
                        attributes.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
                    feature.setAttributes(attributes)
                    layer.dataProvider().addFeature(feature)
                    layer.updateExtents()
                    
                    # Apply styling
                    self._apply_qr_code_symbol(layer, qr_image_path, symbol_settings)
                    
                    # Save to file
                    error = QgsVectorFileWriter.writeAsVectorFormat(
                        layer, save_path, "UTF-8", layer.crs(), "GPKG" if save_path.endswith('.gpkg') else "ESRI Shapefile"
                    )
                    
                    if error[0] != QgsVectorFileWriter.NoError:
                        self.show_error("Error", f"Failed to save layer: {error[1]}")
                        return
                    
                    # Load saved layer
                    saved_layer = QgsVectorLayer(save_path, layer_name, "ogr")
                    if saved_layer.isValid():
                        QgsProject.instance().addMapLayer(saved_layer)
                        # Record history for created permanent layer and feature
                        try:
                            # Attempt to find created feature (match qr_text if possible)
                            created_feature = None
                            from qgis.core import QgsFeatureRequest
                            for f in saved_layer.getFeatures():
                                # Prefer matching qr_text attribute when present
                                try:
                                    if settings_dict.get('store_qr_text') and f.attribute('qr_text') == qr_text:
                                        created_feature = f
                                        break
                                except Exception:
                                    pass
                                if created_feature is None:
                                    created_feature = f
                                    break

                            feature_backup = self.create_feature_backup(created_feature, saved_layer) if created_feature else None

                            self.record_to_history(
                                description=f"Created QR code in new saved layer '{layer_name}'",
                                undo_type='create_feature',
                                can_undo=True,
                                layers=[self.create_layer_descriptor(saved_layer)],
                                features=[feature_backup] if feature_backup else None,
                                meta={'layer_was_created': True}
                            )
                        except Exception:
                            pass

                        if show_confirmation:
                            self.show_info("QR Code Created", f"QR code created in saved layer '{layer_name}'")
                    else:
                        self.show_error("Error", "Failed to load saved layer")
                else:
                    # Create temporary layer
                    qr_layer = self._create_qr_code_layer(
                        layer_name, click_point, canvas_crs, qr_text, qr_image_path, symbol_settings, settings_dict
                    )
                    
                    if not qr_layer:
                        return  # Error already shown
                    
                    # Add layer to project
                    from qgis.core import QgsProject
                    project = QgsProject.instance()
                    project.addMapLayer(qr_layer)
                    # Record history for temporary layer and created feature
                    try:
                        created_feature = None
                        from qgis.core import QgsFeatureRequest
                        for f in qr_layer.getFeatures():
                            try:
                                if settings_dict.get('store_qr_text') and f.attribute('qr_text') == qr_text:
                                    created_feature = f
                                    break
                            except Exception:
                                pass
                            if created_feature is None:
                                created_feature = f
                                break

                        feature_backup = self.create_feature_backup(created_feature, qr_layer) if created_feature else None

                        self.record_to_history(
                            description=f"Created QR code in new layer '{layer_name}'",
                            undo_type='create_feature',
                            can_undo=True,
                            layers=[self.create_layer_descriptor(qr_layer)],
                            features=[feature_backup] if feature_backup else None,
                            meta={'layer_was_created': True}
                        )
                    except Exception:
                        pass

                    if show_confirmation:
                        self.show_info("QR Code Created", f"QR code created in new layer '{layer_name}'")
            
            # Auto zoom if requested
            if auto_zoom:
                from qgis.core import QgsRectangle
                buffer_distance = canvas.mapSettings().mapUnitsPerPixel() * 50  # 50 pixels buffer
                extent = QgsRectangle(
                    click_point.x() - buffer_distance,
                    click_point.y() - buffer_distance,
                    click_point.x() + buffer_distance,
                    click_point.y() + buffer_distance
                )
                canvas.setExtent(extent)
                canvas.refresh()
            
        except Exception as e:
            self.show_error("Error", f"Failed to generate QR code: {str(e)}")


# REQUIRED: Create global instance for automatic discovery
generate_qr_code_canvas_action = GenerateQrCodeCanvasAction()

