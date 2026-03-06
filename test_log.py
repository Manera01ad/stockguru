import logging
from logging.handlers import RotatingFileHandler
import os

_log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
_log_fmt = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')
_file_handler = RotatingFileHandler(
    os.path.join(_log_dir, "stockguru.log"),
    maxBytes=5 * 1024 * 1024,
    backupCount=7
)
_file_handler.setFormatter(_log_fmt)
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_fmt)
logging.basicConfig(level=logging.INFO, handlers=[_file_handler, _console_handler])
log = logging.getLogger("logger_test")

if __name__ == '__main__':
    log.info("Logger test: writing to stockguru.log")
