"""
B.L.A.Z.E Plugin Example — Custom Greeting
Place this file in ~/.blaze/plugins/ and it will auto-load on next server start.

HOW PLUGINS WORK:
  - The plugin manager scans ~/.blaze/plugins/ for .py files on startup
  - Each file must define a register() function that returns an object
    with a handle(tag, arg) method
  - The LLM can trigger your plugin by outputting [SYSTEM:your_tag:argument]
  - handle() returns a string result shown to the user, or None to pass through

ALL BUILT-IN SYSTEM TAGS (for reference — these are already handled by the engine):
  [SYSTEM:open_app:name]           open an app or website
  [SYSTEM:web_search:query]        google search
  [SYSTEM:open_url:url]            open a specific URL
  [SYSTEM:weather]                 current weather
  [SYSTEM:system_stats]            CPU / RAM / disk
  [SYSTEM:news]                    top headlines
  [SYSTEM:organize_downloads]      sort downloads folder
  [SYSTEM:find_file:query]         search for a file
  [SYSTEM:disk_summary]            disk usage breakdown
  [SYSTEM:list_processes]          top running processes
  [SYSTEM:add_reminder:msg|HH:MM]  set a reminder
  [SYSTEM:list_reminders]          show pending reminders
  [SYSTEM:save_note:title|content] save a note
  [SYSTEM:search_notes:query]      search notes
  [SYSTEM:vault_set:key|value]     store in encrypted vault
  [SYSTEM:vault_get:key]           retrieve from vault
  [SYSTEM:vault_list]              list vault keys
  [SYSTEM:define:word]             dictionary definition
  [SYSTEM:wiki:topic]              wikipedia summary
  [SYSTEM:currency:amt|FROM|TO]    currency conversion
  [SYSTEM:github_repos:username]   list github repos
  [SYSTEM:github_trending]         trending github repos
  [SYSTEM:open_drive]              open google drive
  [SYSTEM:search_drive:query]      search google drive
  [SYSTEM:open_spotify:query]      open spotify search
  [SYSTEM:ip_info]                 public IP and location
  [SYSTEM:top_commands]            most used commands
  [SYSTEM:clear_history]           clear conversation history
  [SYSTEM:habit_summary]           weekly usage summary
  [SYSTEM:feedback_stats]          rating stats

  Any tag NOT in the list above is passed to the plugin system — that's your hook.
"""

import datetime


class GreetingPlugin:
    """
    Handles the [SYSTEM:custom_greeting] tag.
    Returns a time-aware greeting from BLAZE.
    """

    def handle(self, tag: str, arg: str):
        """
        Called by the plugin manager for every unrecognised system tag.
        Return a string if you handle it, None to pass through to the next plugin.

        Args:
            tag: the command name (e.g. "custom_greeting")
            arg: anything after the colon (e.g. "Kartik") — empty string if none
        """
        if tag == "custom_greeting":
            hour = datetime.datetime.now().hour
            name = arg.strip() or "sir"

            if hour < 6:
                return f"It's the middle of the night, {name}. I hope you have a good reason to be awake."
            elif hour < 12:
                return f"Good morning, {name}. The world awaits."
            elif hour < 17:
                return f"Good afternoon, {name}. Productivity levels are optimal."
            elif hour < 21:
                return f"Good evening, {name}. Time to wind down — or cause chaos. Your choice."
            else:
                return f"Still up, {name}? The best ideas happen at night."

        return None  # not handled by this plugin — pass to next


def register():
    """
    Required entry point. Called by PluginManager on load.
    Must return an object with a handle(tag, arg) method.
    """
    return GreetingPlugin()
