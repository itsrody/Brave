# adblock_processor/config.py
import configparser
import os
from .utils.exceptions import ConfigError

DEFAULT_CONFIG = {
    'settings': {
        'log_level': 'INFO',
        'log_file': 'adblock_processor.log',
        'output_file': 'output/unified_brave_list.txt',
        'max_parallel_downloads': '5',
        'max_processing_workers': str(os.cpu_count() or 1), # Default to number of CPUs
        'translation_strategy': 'comment_out_untranslatable', # or 'drop_untranslatable'
    },
    'filter_lists': {
        # Example:
        # ublock_origin_filters = https://raw.githubusercontent.com/uBlockOrigin/uAssets/master/filters/filters.txt
        # adguard_base_filters = https://filters.adtidy.org/extension/chromium/filters/2.txt
        # easylist = https://easylist.to/easylist/easylist.txt
    }
}

class AppConfig:
    """
    Application configuration class.
    Loads settings from a config file or uses defaults.
    """
    def __init__(self, config_file_path='config.ini'):
        self.config_file_path = config_file_path
        self.parser = configparser.ConfigParser(interpolation=None) # interpolation=None to treat % as literal
        self._load_config()

    def _load_config(self):
        """Loads configuration from the file, creating it with defaults if it doesn't exist."""
        if not os.path.exists(self.config_file_path):
            print(f"INFO: Configuration file '{self.config_file_path}' not found. Creating with default values.")
            self._create_default_config()
        
        try:
            self.parser.read(self.config_file_path)
        except configparser.Error as e:
            raise ConfigError(f"Error parsing configuration file '{self.config_file_path}': {e}")

        # Ensure default sections exist if user created an empty file
        for section, options in DEFAULT_CONFIG.items():
            if not self.parser.has_section(section):
                self.parser.add_section(section)
            for key, value in options.items():
                if not self.parser.has_option(section, key):
                    self.parser.set(section, key, value)
        
        # Save back to ensure all defaults are written if some were missing
        with open(self.config_file_path, 'w') as f:
            self.parser.write(f)


    def _create_default_config(self):
        """Creates a default configuration file."""
        for section, options in DEFAULT_CONFIG.items():
            self.parser.add_section(section)
            for key, value in options.items():
                self.parser.set(section, key, value)
        
        try:
            os.makedirs(os.path.dirname(self.config_file_path) or '.', exist_ok=True)
            with open(self.config_file_path, 'w') as configfile:
                self.parser.write(configfile)
        except IOError as e:
            raise ConfigError(f"Could not write default configuration file to '{self.config_file_path}': {e}")

    def get(self, section, option, fallback=None):
        """Get a configuration value."""
        try:
            return self.parser.get(section, option, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            if fallback is not None:
                return fallback
            # Try to get from DEFAULT_CONFIG if completely missing
            if section in DEFAULT_CONFIG and option in DEFAULT_CONFIG[section]:
                return DEFAULT_CONFIG[section][option]
            raise ConfigError(f"Option '{option}' not found in section '{section}' and no fallback provided.")

    def getint(self, section, option, fallback=None):
        try:
            return self.parser.getint(section, option, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            if fallback is not None:
                return fallback
            if section in DEFAULT_CONFIG and option in DEFAULT_CONFIG[section]:
                 try:
                    return int(DEFAULT_CONFIG[section][option])
                 except ValueError:
                    raise ConfigError(f"Default value for '{option}' in section '{section}' is not a valid integer.")
            raise ConfigError(f"Option '{option}' not found in section '{section}' and no fallback provided.")

    def getboolean(self, section, option, fallback=None):
        try:
            return self.parser.getboolean(section, option, fallback=fallback)
        except (configparser.NoSectionError, configparser.NoOptionError):
            if fallback is not None:
                return fallback
            if section in DEFAULT_CONFIG and option in DEFAULT_CONFIG[section]:
                val = DEFAULT_CONFIG[section][option].lower()
                if val in ['true', 'yes', '1', 'on']:
                    return True
                if val in ['false', 'no', '0', 'off']:
                    return False
                raise ConfigError(f"Default value for '{option}' in section '{section}' is not a valid boolean.")
            raise ConfigError(f"Option '{option}' not found in section '{section}' and no fallback provided.")

    def get_filter_lists(self):
        """Returns a dictionary of filter list names and their URLs."""
        if self.parser.has_section('filter_lists'):
            return dict(self.parser.items('filter_lists'))
        return {}

# Example usage (typically in main.py)
# config = AppConfig()
# log_level = config.get('settings', 'log_level')
# filter_urls = config.get_filter_lists()
