"""The aws submodule contains classes representing AWS resources

This module contains classes representing AWS resources:
    - DockerRepo : AWS ECR repository
    - BatchJob : AWS Batch job

For each class, you may specify an identifier for an existing AWS resource
or specify parameters to create a new resource on AWS. Higher level resources
(e.g. ComputeEnvironment) take subordinate resources (e.g. IamRole) as input.
"""

from .base_classes import *
from .batch import *
from .ecr import *
