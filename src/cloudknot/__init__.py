"""Cloudknot is a python library to run your existing code on AWS Batch."""

import errno
import logging
import os
import shutil
import subprocess

from . import (
    aws,  # noqa
    config,  # noqa
)
from .aws.base_classes import (  # noqa  # noqa  # noqa  # noqa
    BucketInfo,
    ProfileInfo,
    get_ecr_repo,
    get_profile,
    get_region,
    get_s3_params,
    list_profiles,
    refresh_clients,
    set_ecr_repo,
    set_profile,
    set_region,
    set_s3_params,
)
from .cloudknot import *  # noqa
from .dockerimage import *  # noqa

if shutil.which("docker") is None:
    raise FileNotFoundError(
        "Could not find the 'docker' executable in your PATH."
        "To install Docker, consult https://docs.docker.com/engine/installation"
    )

try:
    subprocess.check_call(
        ["docker", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
except FileNotFoundError:
    raise RuntimeError(
        "It looks like you don't have Docker installed. Please go to https://docs.docker.com/engine/install to install it. Once installed, make sure that the Docker daemon is running before using cloudknot."
    ) from None
except subprocess.CalledProcessError:
    raise RuntimeError(
        "Docker daemon is not responding. Please go to https://docs.docker.com/engine/install for instructions on launching the Docker daemon."
    ) from None

module_logger = logging.getLogger(__name__)

# get the log level from environment variable
if "CLOUDKNOT_LOGLEVEL" in os.environ:
    loglevel = os.environ["CLOUDKNOT_LOGLEVEL"]
    module_logger.setLevel(getattr(logging, loglevel.upper()))
else:
    module_logger.setLevel(logging.WARNING)

# create a file handler
logpath = os.path.join(os.path.expanduser("~"), ".cloudknot", "cloudknot.log")

# Create the config directory if it doesn't exist
logdir = os.path.dirname(logpath)
try:
    os.makedirs(logdir)
except OSError as e:
    pre_existing = e.errno == errno.EEXIST and os.path.isdir(logdir)
    if pre_existing:
        pass
    else:  # pragma: nocover
        raise e

handler = logging.FileHandler(logpath, mode="w")
handler.setLevel(logging.DEBUG)

# create a logging format
formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
handler.setFormatter(formatter)

# add the handlers to the logger
module_logger.addHandler(handler)
module_logger.info("Started new cloudknot session")

logging.getLogger("boto").setLevel(logging.WARNING)
logging.getLogger("boto3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
