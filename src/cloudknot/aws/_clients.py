from concurrent.futures import thread
import typing
import logging
import boto3
import botocore.client
import botocore.config

from .base_classes import get_profile, get_region

from wrapt import synchronized
from functools import cached_property

if typing.TYPE_CHECKING:
    from mypy_boto3_batch import BatchClient
    from mypy_boto3_cloudformation import CloudFormationClient
    from mypy_boto3_ecr import ECRClient
    from mypy_boto3_ecs import ECSClient
    from mypy_boto3_ec2 import EC2Client
    from mypy_boto3_iam import IAMClient
    from mypy_boto3_s3 import S3Client

mod_logger = logging.getLogger(__name__)


CLIENT_NAMES = {"batch", "cloudformation", "ecr", "ecs", "ec2", "iam", "s3"}
__all__ = ["CloudKnotClients"]


_clients = {}

import threading
class CloudKnotClients:
    """Class for managing AWS clients."""

    def __init__(self, boto_config: typing.Optional[botocore.config.Config] = None):
        self.boto_config = boto_config or botocore.config.Config()
        self._clients = {}
        self._clients_lock = threading.RLock()
    
    def _make_client(self, service_name: str):
        return boto3.Session(profile_name=get_profile()).client(
            service_name="batch",
            region_name=get_region(),
            config=self.boto_config,
        )
    
    @cached_property
    @synchronized
    def batch(self) -> BatchClient: 
        return self._make_client("batch")
    
    @cached_property
    @synchronized
    def cloudformation(self) -> CloudFormationClient:
        return self._make_client("cloudformation")
    
    @cached_property
    @synchronized
    def ecr(self) -> ECRClient:
        return self._make_client("ecr")
    
    @cached_property
    @synchronized
    def ecs(self) -> ECSClient:
        return self._make_client("ecs")
    
    @cached_property
    @synchronized
    def ec2(self) -> EC2Client:
        return self._make_client("ec2")
    
    @cached_property
    @synchronized
    def iam(self) -> IAMClient:
        return self._make_client("iam")
    
    @cached_property
    @synchronized
    def s3(self) -> S3Client:
        return self._make_client("s3")
    

    @synchronized
    def reset(self):
        """Reset all clients."""
        for client_name in CLIENT_NAMES:
            self.__dict__.pop(client_name, None)
