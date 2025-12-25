"""
Configuration management for saving and loading tab layouts.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from platformdirs import user_config_dir


class TabConfiguration:
    """Manages saving and loading of tab configurations."""

    @staticmethod
    def save_configuration(file_path: str, tabs_data: List[Dict[str, Any]]) -> bool:
        """
        Save tab configuration to a JSON file.

        Args:
            file_path: Path to save the configuration file
            tabs_data: List of tab configurations, each containing:
                - name: Tab name
                - channels: List of channel names plotted in this tab

        Returns:
            True if successful, False otherwise
        """
        try:
            config = {
                'version': '1.0',
                'tabs': tabs_data
            }

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2)

            return True
        except Exception as e:
            print(f"Error saving configuration: {e}")
            return False

    @staticmethod
    def load_configuration(file_path: str) -> Optional[List[Dict[str, Any]]]:
        """
        Load tab configuration from a JSON file.

        Args:
            file_path: Path to the configuration file

        Returns:
            List of tab configurations, or None if failed
        """
        try:
            if not Path(file_path).exists():
                return None

            with open(file_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            # Validate configuration
            if 'version' not in config or 'tabs' not in config:
                print("Invalid configuration file format")
                return None

            # For now, only support version 1.0
            if config['version'] != '1.0':
                print(f"Unsupported configuration version: {config['version']}")
                return None

            return config['tabs']

        except Exception as e:
            print(f"Error loading configuration: {e}")
            return None

    @staticmethod
    def get_default_config_dir() -> Path:
        """Get the default configuration directory (platform-specific)."""
        # Windows: %APPDATA%\MFViewer (e.g., C:\Users\username\AppData\Roaming\MFViewer)
        # macOS: ~/Library/Application Support/MFViewer
        # Linux: ~/.config/mfviewer (XDG-compliant)
        config_dir = Path(user_config_dir("MFViewer", "MFViewer"))
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir

    @staticmethod
    def save_session(file_path: str, tabs_data: List[Dict[str, Any]], last_log_file: Optional[str] = None,
                    last_directory: Optional[str] = None, last_config_file: Optional[str] = None) -> bool:
        """
        Save session state (last file + tab config).

        Args:
            file_path: Path to save the session file
            tabs_data: List of tab configurations
            last_log_file: Path to the last opened log file
            last_directory: Last directory used for file dialogs
            last_config_file: Path to the last loaded tab configuration file

        Returns:
            True if successful, False otherwise
        """
        try:
            session = {
                'version': '1.0',
                'last_log_file': last_log_file,
                'last_directory': last_directory,
                'last_config_file': last_config_file,
                'tabs': tabs_data
            }

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(session, f, indent=2)

            return True
        except Exception as e:
            print(f"Error saving session: {e}")
            return False

    @staticmethod
    def load_session(file_path: str) -> Optional[Dict[str, Any]]:
        """
        Load session state from file.

        Args:
            file_path: Path to the session file

        Returns:
            Dictionary with 'last_log_file' and 'tabs', or None if failed
        """
        try:
            if not Path(file_path).exists():
                return None

            with open(file_path, 'r', encoding='utf-8') as f:
                session = json.load(f)

            # Validate session
            if 'version' not in session:
                print("Invalid session file format")
                return None

            if session['version'] != '1.0':
                print(f"Unsupported session version: {session['version']}")
                return None

            return {
                'last_log_file': session.get('last_log_file'),
                'last_directory': session.get('last_directory'),
                'last_config_file': session.get('last_config_file'),
                'tabs': session.get('tabs', [])
            }

        except Exception as e:
            print(f"Error loading session: {e}")
            return None

    @staticmethod
    def get_session_file() -> Path:
        """Get the path to the session file."""
        return TabConfiguration.get_default_config_dir() / 'last_session.json'
