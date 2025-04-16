import logging, os
from dotenv import load_dotenv

load_dotenv()


def setup_custom_logger(
    name: str = "main",
    file_path: str = os.environ.get("LOG_DIR"),
    file_level: int = logging.DEBUG,
    console_level: int = logging.INFO,
    file_format: str = '%(asctime)s - %(filename)s:%(lineno)d - %(levelname)s - %(message)s',
    console_format: str = '%(filename)s:%(lineno)d - %(levelname)s - %(message)s'
) -> logging.Logger:
    """
    Set up a custom logger with separate file and console handlers, each with its own level and formatter.

    Parameters:
        name (str): The name of the logger.
        file_path (str): The path of the file to log messages.
        file_level (int): Logging level for the file handler. Default is logging.DEBUG.
        console_level (int): Logging level for the console handler. Default is logging.INFO.
        file_format (str): Formatter string for the file handler.
        console_format (str): Formatter string for the console handler.

    Returns:
        logging.Logger: The configured logger.
    """
    # Create a custom logger
    logger = logging.getLogger(name)
    logger.setLevel(min(file_level, console_level))  # Ensure logger level is low enough for both handlers
    logger.propagate = False  # Avoid duplicating logs if root logger is configured

    # Create and set formatter for the file handler
    file_formatter = logging.Formatter(file_format)
    file_handler = logging.FileHandler(os.path.join(file_path, name), mode='a')
    file_handler.setLevel(file_level)
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Create and set formatter for the console handler
    console_formatter = logging.Formatter(console_format)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(console_level)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger

logger = setup_custom_logger("main")