import logging
from functools import cached_property
from typing import Literal, get_args, Optional, overload

import boto3
import botocore.config
from mypy_boto3_batch import BatchClient
from mypy_boto3_cloudformation import CloudFormationClient
from mypy_boto3_ec2 import EC2Client
from mypy_boto3_ecr import ECRClient
from mypy_boto3_ecs import ECSClient
from mypy_boto3_iam import IAMClient
from mypy_boto3_s3 import S3Client
from wrapt.decorators import synchronized
from .base_classes import get_profile, get_region

from threading import RLock

__all__ = ["CloudknotClients"]

mod_logger = logging.getLogger(__name__)

ClientNameType = Literal["batch", "cloudformation", "ecr", "ecs", "ec2", "iam", "s3"]

class CloudknotClients:
    """Holds all the boto3 clients used by cloudknot."""

    def __init__(self, max_pool_connections: int = 10):
        self._max_pool_connections = max_pool_connections
        self._client_locks = {client_name: RLock() for client_name in get_args(ClientNameType)}

    @overload
    def _make_client(self, service_name: Literal["batch"], session: Optional[boto3.Session] = None, config: Optional[botocore.config.Config] = None) -> BatchClient: ...

    @overload
    def _make_client(self, service_name: Literal["cloudformation"], session: Optional[boto3.Session] = None, config: Optional[botocore.config.Config] = None) -> CloudFormationClient: ...

    @overload
    def _make_client(self, service_name: Literal["ecr"], session: Optional[boto3.Session] = None, config: Optional[botocore.config.Config] = None) -> ECRClient: ...

    @overload
    def _make_client(self, service_name: Literal["ecs"], session: Optional[boto3.Session] = None, config: Optional[botocore.config.Config] = None) -> ECSClient: ...

    @overload
    def _make_client(self, service_name: Literal["ec2"], session: Optional[boto3.Session] = None, config: Optional[botocore.config.Config] = None) -> EC2Client: ...

    @overload
    def _make_client(self, service_name: Literal["iam"], session: Optional[boto3.Session] = None, config: Optional[botocore.config.Config] = None) -> IAMClient: ...

    @overload
    def _make_client(self, service_name: Literal["s3"], session: Optional[boto3.Session] = None, config: Optional[botocore.config.Config] = None) -> S3Client: ...

    def _make_client(
        self,
        service_name: ClientNameType,
        session: Optional[boto3.Session] = None,
        config: Optional[botocore.config.Config] = None,
    ):
        """Make a boto3 client."""
        mod_logger.debug(f"Creating boto3 client for {service_name}")
        session = session or boto3.session.Session(profile_name=get_profile(fallback=None), region_name=get_region())
        return session.client(
            service_name,
            region_name=get_region(),
            config=config or botocore.config.Config(max_pool_connections=self._max_pool_connections),
        )

    @cached_property
    def batch(self) -> BatchClient:
        """Returns a batch client."""
        with self._client_locks["batch"]:
            return self._make_client("batch")

    @cached_property
    def cloudformation(self) -> CloudFormationClient:
        """Returns a cloudformation client."""
        with self._client_locks["cloudformation"]:
            return self._make_client("cloudformation")

    @cached_property
    def ecr(self) -> ECRClient:
        """Returns an ecr client."""
        with self._client_locks["ecr"]:
            return self._make_client("ecr")

    @cached_property
    def ecs(self) -> ECSClient:
        """Returns an ecs client."""
        with self._client_locks["ecs"]:
            return self._make_client("ecs")

    @cached_property
    def ec2(self) -> EC2Client:
        """Returns an ec2 client."""
        with self._client_locks["ec2"]:
            return self._make_client("ec2")

    @cached_property
    def iam(self) -> IAMClient:
        """Returns an iam client."""
        with self._client_locks["iam"]:
            return self._make_client("iam")

    @cached_property
    def s3(self) -> S3Client:
        """Returns an s3 client."""
        with self._client_locks["s3"]:
            return self._make_client("s3")

    def reset(self):
        """Reset all clients."""
        for client_name in get_args(ClientNameType):
            with self._client_locks[client_name]:
                if client := self.__dict__.pop(client_name, None):
                    client.close()
                    mod_logger.debug(f"Reset boto3 client for {client_name}")

    def refresh(self, create_all: bool = False):
        """Reset and refresh all clients."""
        self.reset()
        to_create = get_args(ClientNameType) if create_all else self.__dict__.keys() & get_args(ClientNameType)
        for client_name in to_create:
            with self._client_locks[client_name]:
                mod_logger.debug(f"Creating boto3 client for {client_name}")
                getattr(self, client_name)
            mod_logger.debug(f"Refreshed boto3 clients: {to_create}")
