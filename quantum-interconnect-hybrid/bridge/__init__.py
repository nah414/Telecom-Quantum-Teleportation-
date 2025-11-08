"""Bridge package exposing the dcq reference loop and sample plugin."""

from .qcs_dcq_bridge import main as bridge_main  # re-export for convenience
from .dcq_plugin import main as plugin_main

__all__ = ["bridge_main", "plugin_main"]
