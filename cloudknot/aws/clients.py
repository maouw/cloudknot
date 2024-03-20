from typing import TypeVar

import botocore.client
from mypy_boto3_batch import BatchClient
from mypy_boto3_cloudformation import CloudFormationClient
from mypy_boto3_ec2 import EC2Client
from mypy_boto3_ecr.client import ECRClient
from mypy_boto3_ecs import ECSClient
from mypy_boto3_iam.client import IAMClient
from mypy_boto3_s3 import S3Client

BaseClientType = TypeVar("BaseClientType", bound=botocore.client.BaseClient)

__all__ = ["CloudknotClients"]


class CloudknotClients:
    def __init__(self, dict_: dict):
        self.__dict__ = dict_

    @property
    def batch(self) -> BatchClient:
        return self.__dict__.get("batch")

    @property
    def cloudformation(self) -> CloudFormationClient:
        return self.__dict__.get("cloudformation")

    @property
    def ecr(self) -> ECRClient:
        return self.__dict__.get("ecr")

    @property
    def ecs(self) -> ECSClient:
        return self.__dict__.get("ecs")

    @property
    def ec2(self) -> EC2Client:
        return self.__dict__.get("ec2")

    @property
    def iam(self) -> IAMClient:
        return self.__dict__.get("iam")

    @property
    def s3(self) -> S3Client:
        return self.__dict__.get("s3")

    def __contains__(self, item):
        return item in self.__dict__

    def __iter__(self):
        return iter(self.__dict__)

    def __len__(self):
        return len(self.__dict__)

    def __getitem__(self, item):
        return self.__dict__[item]
