
import logging
import os
import datetime
from typing import Optional
from time import struct_time

from pytz import timezone, all_timezones


# https://medium.com/@reach.117.war/time-zone-logging-headache-and-a-workaround-in-python-7f96b403b07a
def get_tz(tz):
    def new_converter(_unused_param, sec):
        return TimeZoneConverter(tz).converter(sec)
    return new_converter


class LoggerFactory:
    def __init__(self, console_logging_level=logging.DEBUG,
                 do_file_logging=True, file_logging_level=logging.DEBUG, file_logging_dir="./logs",
                 time_zone_str: str='UTC'):
        """
        Args:
            time_zone_str: See https://mljar.com/blog/list-pytz-timezones/
        """
        self.console_logging_level = loglevel_string_to_int(console_logging_level) if isinstance(console_logging_level, str) \
            else console_logging_level
        self.do_file_logging = do_file_logging
        self.file_logging_level = loglevel_string_to_int(file_logging_level) if isinstance(file_logging_level, str) \
            else file_logging_level
        print("Configured time zone for logger: {}".format(time_zone_str))
        logging.Formatter.converter = get_tz(time_zone_str) # type: ignore
        if do_file_logging:
            if not file_logging_dir:
                raise ValueError("Invalid file_logging_dir")
            os.makedirs(file_logging_dir, exist_ok=True)
            self.file_logging_path = os.path.join(file_logging_dir,
                "[{}]_BrReconciler_logs.txt".format(datetime.datetime.strftime(datetime.datetime.now(), "%Y%m%dT%H%M%S")))
            print("File logging: {}".format(self.file_logging_path))
    
    def get_logger(self, name: Optional[str]) -> logging.Logger:
        min_logging_level = self.console_logging_level
        if self.do_file_logging:
            min_logging_level = min(min_logging_level, self.file_logging_level)

        logger = logging.getLogger(name)
        logger.propagate = False
        logger.setLevel(min_logging_level)
        logger.handlers.clear()

        console_logging_formatter = logging.Formatter(
           "[%(asctime)s %(levelname)-5s][%(name)s] %(message)s",
            datefmt="%H:%M:%S",
        )
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(console_logging_formatter)
        console_handler.setLevel(self.console_logging_level)
        logger.addHandler(console_handler)

        if self.do_file_logging:
            file_logging_formatter = logging.Formatter(
                "[%(asctime)s %(levelname)-8s][%(name)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            file_handler = logging.FileHandler(self.file_logging_path, mode='a', encoding='utf-8')
            file_handler.setFormatter(file_logging_formatter)
            file_handler.setLevel(self.file_logging_level)
            logger.addHandler(file_handler)
        return logger


def loglevel_string_to_int(loglevel_str: str):
    match loglevel_str.lower():
        case 'debug':
            return logging.DEBUG
        case 'info':
            return logging.INFO
        case 'warning':
            return logging.WARNING
        case 'error':
            return logging.ERROR
        case _:
            raise ValueError("Unknown log level string: {}".format(loglevel_str))


class TimeZoneConverter:
    def __init__(self, tz):
        self.tz : str = tz

    def _valid_timezone(self) -> bool:
        return self.tz is not None \
            and self.tz != "" \
            and self.tz in all_timezones

    def _get_timezone(self) -> str:
        if not self._valid_timezone():
            raise ValueError("Not valid timezone code")
        return self.tz

    def converter(self, _unused_sec: float) -> struct_time:
        tz = self._get_timezone()
        return datetime.datetime.now(timezone(tz)).timetuple()
