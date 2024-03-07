"""Cloudknot is a python library to run your existing code on AWS Batch."""

import logging
import os
import subprocess
import shutil
import inspect
import typing

from . import aws  # noqa
from . import config  # noqa
from .aws.base_classes import get_profile, set_profile, list_profiles  # noqa
from .aws.base_classes import get_region, set_region  # noqa
from .aws.base_classes import get_ecr_repo, set_ecr_repo  # noqa
from .aws.base_classes import get_s3_params, set_s3_params  # noqa
from .aws.base_classes import refresh_clients  # noqa
from .cloudknot import *  # noqa
from .dockerimage import *  # noqa
from ._version import version as __version__  # noqa

if shutil.which("docker") is None:
    raise FileNotFoundError(
        "Could not find the 'docker' executable in your PATH. To install Docker, consult https://docs.docker.com/engine/installation"
    )

try:
    subprocess.check_call(
        ["docker", "--version"],
        shell=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
except subprocess.CalledProcessError as e:
    raise RuntimeError("Could not run 'docker --version'. Is Docker running?") from e


class StrFmtStyleLoggerAdapter(logging.LoggerAdapter):
    """
    Use {}-style format specifiers in log messages.

    This is a `logging.LoggerAdapter` subclass that adds support for {}-style format specifiers to the
    `logging.Logger.log` method.

    """

    _log_param_names = inspect.signature(logging.Logger.log).parameters.keys()

    def log(
        self,
        level: int,
        msg: str,
        *args,
        fmt_vars: (typing.Mapping | None) = None,
        **kwargs,
    ):
        """Log a message with {}-style format specifiers, possibly passing arguments to `str.format`.

        Parameters
        ----------
        level: int
            The level to log the message at (passed to `logging.Logger.log`)
        msg: str
            The message to log, possibly containing {}-style format specifiers for `str.format`
        *args: tuple
            The positional arguments to format the message with
        fmt_vars: dict-like (optional)
            A mapping of keyword arguments to format the message with, passed to `str.format`
        **kwargs: dict (optional)
            Any keyword arguments that are not in the signature of `logging.Logger.log` are passed to `str.format`
            Reserved names as per the signature of `logging.Logger.log` in Python 3.12 are:
                ('self', 'level', 'msg', 'args', 'exc_info', 'extra', 'stack_info', 'stacklevel')
            Any other keyword arguments are added to `fmt_vars` and passed to `str.format` as keyword arguments.

        """
        if self.isEnabledFor(level):
            msg, kwargs = self.process(msg, kwargs)
            stacklevel = kwargs.pop("stacklevel", 1)
            fmt_vars = dict(fmt_vars or {})
            fmt_vars.update(
                {
                    k: kwargs.pop(k)
                    for k in tuple(kwargs.keys())
                    if k not in self._log_param_names
                }
            )
            self.logger.log(
                level,
                msg.format(*args, **fmt_vars, **kwargs, stacklevel=stacklevel + 1),
            )


module_logger = StrFmtStyleLoggerAdapter(logging.getLogger(__name__))

# get the log level from environment variable:
module_logger.setLevel(
    getattr(logging, os.environ.get("CLOUDKNOT_LOGLEVEL", "").upper(), logging.WARNING)
)

# create a file handler
logpath = os.path.join(os.path.expanduser("~"), ".cloudknot", "cloudknot.log")

# Create the config directory if it doesn't exist
logdir = os.path.dirname(logpath)
os.makedirs(logdir, exist_ok=True)

handler = logging.FileHandler(logpath, mode="w")
handler.setLevel(logging.DEBUG)

# create a logging format
formatter = logging.Formatter(
    "{asctime} - {name} - {levelname} - {message}",
    style="{",
    datefmt="%Y-%m-%d %H:%M:%S",
)
handler.setFormatter(formatter)

# add the handlers to the logger
module_logger.logger.addHandler(handler)
module_logger.info("Started new cloudknot session")

logging.getLogger("boto").setLevel(logging.WARNING)
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
