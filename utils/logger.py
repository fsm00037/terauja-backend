import logging
import logging.config
import sys
from datetime import datetime
from colorama import init, Fore, Style

# Initialize colorama
init(autoreset=True)

class CustomFormatter(logging.Formatter):
    """Custom formatter to add colors and timestamps"""
    
    # Colors for different levels
    LEVEL_COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.BLUE,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
        # Custom level for success
        25: Fore.GREEN
    }

    def formatMessage(self, record):
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        level_name = record.levelname
        if record.levelno == 25:
            level_name = "SUCCESS"
        
        color = self.LEVEL_COLORS.get(record.levelno, "")
        
        # Ensure record.message is computed if not already present
        if not hasattr(record, 'message'):
            record.message = record.getMessage()
            
        # Format: [2024-04-09 10:00:00] [INFO] - Message
        return f"{Style.DIM}[{timestamp}]{Style.RESET_ALL} {color}[{level_name:7}]{Style.RESET_ALL} - {record.message}"

# Create Success level
SUCCESS_LEVEL_NUM = 25
logging.addLevelName(SUCCESS_LEVEL_NUM, "SUCCESS")

def success(self, message, *args, **kws):
    if self.isEnabledFor(SUCCESS_LEVEL_NUM):
        self._log(SUCCESS_LEVEL_NUM, message, args, **kws)

logging.Logger.success = success

# Configuration for Uvicorn and Custom Logger
LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "custom": {
            "()": CustomFormatter,
        },
        "standard": {
            "format": "[%(asctime)s] [%(levelname)s] - %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "custom",
            "stream": "ext://sys.stdout",
        },
        "file": {
            "class": "logging.FileHandler",
            "formatter": "standard",
            "filename": "server.log",
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "psicouja": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.error": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
        "uvicorn.access": {
            "handlers": ["console", "file"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

def setup_logger():
    # Apply centralized configuration
    logging.config.dictConfig(LOGGING_CONFIG)
    
    # Silenciar ruidos externos
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    
    return logging.getLogger("psicouja")

# Singleton instance
logger = setup_logger()
