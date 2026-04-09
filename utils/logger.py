import logging
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
        
        # Format: [2024-04-09 10:00:00] [INFO] - Message
        return f"{Style.DIM}[{timestamp}]{Style.RESET_ALL} {color}[{level_name:7}]{Style.RESET_ALL} - {record.message}"

# Create Success level
SUCCESS_LEVEL_NUM = 25
logging.addLevelName(SUCCESS_LEVEL_NUM, "SUCCESS")

def success(self, message, *args, **kws):
    if self.isEnabledFor(SUCCESS_LEVEL_NUM):
        self._log(SUCCESS_LEVEL_NUM, message, args, **kws)

logging.Logger.success = success

def setup_logger():
    # Root logger
    logger = logging.getLogger("psicouja")
    logger.setLevel(logging.INFO)
    logger.propagate = False  # Evitar duplicados si el root logger tiene handlers
    
    # Check if we already have a handler to avoid duplicates
    if not logger.handlers:
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(CustomFormatter())
        logger.addHandler(console_handler)
        
        # file handler
        file_handler = logging.FileHandler("server.log", encoding="utf-8")
        file_formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] - %(message)s")
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # Silenciar ruidos externos
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    
    return logger

# Singleton instance
logger = setup_logger()
