import re
from typing import Literal, TypeVar, get_args

import botocore.config
import boto3
import logging

from .base_classes import get_profile, get_region
from mypy_boto3_batch import BatchClient
from mypy_boto3_cloudformation import CloudFormationClient
from mypy_boto3_ec2 import EC2Client
from mypy_boto3_ecr.client import ECRClient
from mypy_boto3_ecs import ECSClient
from mypy_boto3_iam.client import IAMClient
from mypy_boto3_s3 import S3Client
from functools import cached_property

__all__ = ["CloudknotClients"]

mod_logger = logging.getLogger(__name__)


class CloudknotClients:
    """Holds all the boto3 clients used by cloudknot."""

    __CLIENT_NAMES: Literal["batch", "cloudformation", "ecr", "ecs", "ec2", "iam", "s3"]

    def __init__(self):
        self._max_pool_connections = 10

    @cached_property
    def boto_config(self) -> botocore.config.Config:
        """Returns a botocore config object with the specified max_pool_connections."""
        return botocore.config.Config(
            max_pool_connections=self._max_pool_connections, **kwargs
        )

    @cached_property
    def boto_session(self) -> boto3.Session:
        """Returns a boto3 session object with the specified profile."""
        return boto3.Session(profile_name=get_profile(fallback=None))

    def _make_client(self, client_name: str):
        """Make a boto3 client."""
        mod_logger.debug(f"Creating boto3 client for {client_name}")
        return self.boto_session.client(
            client_name, region_name=get_region(), config=self.boto_config
        )  # type: ignore

    @cached_property
    def batch(self) -> BatchClient:
        """Returns a batch client."""
        return self._make_client("batch")

    @cached_property
    def cloudformation(self) -> CloudFormationClient:
        """Returns a cloudformation client."""
        return self._make_client("cloudformation")

    @cached_property
    def ecr(self) -> ECRClient:
        """Returns an ecr client."""
        return self._make_client("ecr")

    @cached_property
    def ecs(self) -> ECSClient:
        """Returns an ecs client."""
        return self._make_client("ecs")

    @cached_property
    def ec2(self) -> EC2Client:
        """Returns an ec2 client."""
        return self._make_client("ec2")

    @cached_property
    def iam(self) -> IAMClient:
        """Returns an iam client."""
        return self._make_client("iam")

    @cached_property
    def s3(self) -> S3Client:
        """Returns an s3 client."""
        return self._make_client("s3")

    def reset(self):
        """Reset all clients."""
        for client_name in get_args(self.__CLIENT_NAMES):
            self.__dict__.pop(client_name, None)
        self.__dict__.pop("boto_config", None)
        self.__dict__.pop("boto_session", None)

    def refresh(self, max_pool_connections: int = 10):
        """Reset and refresh all clients."""
        self.reset()
        self._max_pool_connections = max_pool_connections
        for client_name in get_args(self.__CLIENT_NAMES):
            getattr(self, client_name, None)
