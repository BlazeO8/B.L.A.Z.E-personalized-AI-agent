"""
B.L.A.Z.E — Plugin Manager
Dynamically loads and dispatches Python plugin files from ~/.blaze/plugins/.
Each plugin file should expose a register() function returning an object
with a handle(tag, arg) method.
"""

import importlib.util

from blaze.config import PLUGIN_DIR
from blaze.core.logging_audit import log


class PluginManager:
    def __init__(self):
        self.plugins = {}
        self.load_all()

    def load_all(self):
        for f in PLUGIN_DIR.glob("*.py"):
            self.load(f)

    def load(self, path):
        name = path.stem
        try:
            spec = importlib.util.spec_from_file_location(name, path)
            mod  = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if hasattr(mod, "register"):
                self.plugins[name] = mod.register()
                log.info(f"Plugin loaded: {name}")
        except Exception as e:
            log.error(f"Plugin {name}: {e}")

    def dispatch(self, tag, arg):
        for plugin in self.plugins.values():
            if hasattr(plugin, "handle"):
                result = plugin.handle(tag, arg)
                if result:
                    return result
        return None


# ── Singleton ─────────────────────────────────────────────────────────────────
plugins = PluginManager()
