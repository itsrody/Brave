# adblock_processor/utils/logger.py
import logging
import sys

def setup_logger(name='adblock_processor', log_level_str='INFO', log_file=None):
    """
    Sets up a logger.
    """
    logger = logging.getLogger(name)
    
    # Prevent multiple handlers if already configured
    if logger.hasHandlers():
        logger.handlers.clear()

    log_level = getattr(logging, log_level_str.upper(), logging.INFO)
    logger.setLevel(log_level)

    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console Handler
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    logger.addHandler(stdout_handler)

    # File Handler (optional)
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, mode='a') # Append mode
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except IOError as e:
            logger.error(f"Could not set up log file handler at {log_file}: {e}", exc_info=False)
            # Continue with console logging

    return logger

# Example usage:
# from .config import AppConfig
# config = AppConfig()
# logger = setup_logger(
#     log_level_str=config.get('settings', 'log_level', 'INFO'),
#     log_file=config.get('settings', 'log_file', None)
# )
# logger.info("Logger initialized.")
