

def classFactory(iface):
    """
    Factory function that QGIS calls to instantiate the plugin.
    
    Args:
        iface: QGIS interface instance
        
    Returns:
        RightClickUtilities: Plugin instance
    """
    from .right_click_utilities import RightClickUtilities
    return RightClickUtilities(iface)
