import configparser
import contextlib
import json
import logging
import os
import re
import uuid
from typing import NamedTuple, Optional, TypedDict, Any, cast, get_args, Literal
from functools import partial
from collections.abc import Sequence
import boto3
import botocore
from mypy_boto3_s3.literals import BucketLocationConstraintType, ServerSideEncryptionType
from mypy_boto3_s3.type_defs import TagTypeDef, TaggingTypeDef,CreateBucketConfigurationTypeDef

from ..config import get_config_file, rlock
from .clients import CloudknotClients

__all__ = [
    "BatchJobFailedError",
    "CKTimeoutError",
    "CannotCreateResourceException",
    "CannotDeleteResourceException",
    "CloudknotConfigurationError",
    "CloudknotInputError",
    "NamedObject",
    "ProfileException",
    "RegionException",
    "ResourceClobberedException",
    "ResourceDoesNotExistException",
    "ResourceExistsException",
    "clients",
    "get_ecr_repo",
    "get_profile",
    "get_region",
    "get_s3_params",
    "get_tags",
    "get_user",
    "list_profiles",
    "refresh_clients",
    "set_ecr_repo",
    "set_profile",
    "set_region",
    "set_s3_params",
    "BucketInfo",
    "ProfileInfo",
]
mod_logger = logging.getLogger(__name__)

clients: CloudknotClients = CloudknotClients()

# TagTypeDef definition


def get_tags(
    name: str, additional_tags: Optional[dict[str, Any] | Sequence[dict[str, Any]]] = None
) -> Sequence[TagTypeDef]:
    """Get a list of tags for an AWS resource."""
    match additional_tags:
        case None:
            tag_dict = dict()
        case list():
            try:
                tag_dict = {item["Key"]: item["Value"] for item in additional_tags}
            except KeyError:
                raise ValueError(
                    "If `additional_tags` is a list, it must be a list of dictionaries of the form {'Key': key_val, 'Value': "
                    "value_val}."
                )
        case dict():
            if "Key" in additional_tags or "Value" in additional_tags:
                raise ValueError(
                    "If `additional_tags` is a dict, it cannot contain keys named 'Key' or 'Value'. It looks like you are trying to pass in tags of the form  `{'Key': key_val, 'Value': value_val}`. If that's the case, please put it in a `list`, i.e. `[{'Key': key_val, 'Value': value_val}]`."
                )
            tag_dict = additional_tags
        case _:
            raise ValueError(
                "`additional_tags` must be a `dict` or a `list` of `dict`s."
            )

    tag_dict.setdefault("Name", name)
    tag_dict.setdefault("Owner", get_user())
    tag_dict.setdefault("Environment", "cloudknot")
    return [{"Key": k, "Value": v} for k, v in tag_dict.items()]


def get_ecr_repo() -> str:
    """Get the cloudknot ECR repository.

    First, check the cloudknot config file for the 'ecr-repo' option.
    If that fails, check for the `CLOUDKNOT_ECR_REPO` environment variable.
    If that fails, use 'cloudknot'.

    Returns
    -------
    repo : str
        Cloudknot ECR repository name.
    """
    config_file = get_config_file()
    config = configparser.ConfigParser()

    with rlock:
        config.read(config_file)

        option = "ecr-repo"
        if config.has_section("aws") and config.has_option("aws", option):
            repo = config.get("aws", option)
        else:
            # Get the repo name from an environment variable or use a fallback:
            repo = os.environ.get("CLOUDKNOT_ECR_REPO", "cloudknot")

        # Use set_ecr_repo to check for name availability
        # and write to config file
        set_ecr_repo(repo)
    return repo


def set_ecr_repo(repo: str):
    """Set the cloudknot ECR repo.

    Set repo by modifying the cloudknot config file

    Parameters
    ----------
    repo : str
        Cloudknot ECR repo name.
    """
    # Update the config file
    config_file = get_config_file()
    config = configparser.ConfigParser()

    with rlock:
        config.read(config_file)

        if not config.has_section("aws"):  # pragma: nocover
            config.add_section("aws")

        config.set("aws", "ecr-repo", repo)
        with open(config_file, "w") as f:
            config.write(f)

        # Flake8 will see that repo_arn is set in the try/except clauses
        # and claim that we are referencing it before assignment below
        # so we predefine it here. Also, it should be predefined as a
        # string to pass parameter validation by boto.
        repo_arn = "test"
        try:
            # If repo exists, retrieve its info
            response = clients.ecr.describe_repositories(repositoryNames=[repo])
            repo_arn = response["repositories"][0]["repositoryArn"]
        except clients.ecr.exceptions.RepositoryNotFoundException:
            # If it doesn't exists already, then create it
            response = clients.ecr.create_repository(repositoryName=repo)
            try:
                repo_arn = response["repository"]["repositoryArn"]
            except KeyError:
                raise CloudknotConfigurationError(f"Could not find ARN for repo {repo}")

        clients.ecr.tag_resource(
            resourceArn=repo_arn,
            tags=get_tags(
                name=repo,
                additional_tags={"Project": "Cloudknot global config"},
            ),
        )


class BucketInfo(NamedTuple):
    """A NamedTuple with fields ('bucket', 'policy', 'policy_arn', 'sse')."""

    bucket: str
    policy: str
    policy_arn: str
    sse: Optional[ServerSideEncryptionType]


def get_s3_params() -> BucketInfo:
    """Get the cloudknot S3 bucket and corresponding access policy.

    For the bucket name, first check the cloudknot config file for the bucket
    option. If that fails, check for the CLOUDKNOT_S3_BUCKET environment
    variable. If that fails, use
    'cloudknot-' + get_user().lower() + '-' + uuid4()

    For the policy name, first check the cloudknot config file. If that fails,
    use 'cloudknot-bucket-access-' + str(uuid.uuid4())

    For the region, first check the cloudknot config file. If that fails,
    use the current cloudknot region

    Returns
    -------
    :
        A NamedTuple with fields ('bucket', 'policy', 'policy_arn', 'sse')
    """
    config_file = get_config_file()
    config = configparser.ConfigParser()

    with rlock:
        config.read(config_file)

        option = "s3-bucket-policy"
        if config.has_section("aws") and config.has_option("aws", option):
            # Get policy name from the config file
            policy = config.get("aws", option)
        else:
            # or set policy to None to create it in the call to
            # set_s3_params()
            policy = None

        option = "s3-bucket"
        if config.has_section("aws") and config.has_option("aws", option):
            bucket = config.get("aws", option)
        else:
            bucket = os.getenv(
                "CLOUDKNOT_S3_BUCKET", # Get the bucket name from an environment variable
                "cloudknot-" + get_user().lower() + "-" + str(uuid.uuid4()) # Use the fallback bucket b/c the cloudknot bucket environment variable is not set
            )

            if policy is not None:
                # In this case, the bucket name is new, but the policy is not.
                # Update the policy to reflect the new bucket name.
                update_s3_policy(policy=policy, bucket=bucket)

        option = "s3-sse"
        if config.has_section("aws") and config.has_option("aws", option):
            sse = config.get("aws", option)
            if sse not in (valid_sse_names := get_args(ServerSideEncryptionType) + ("None",)): # Check if the sse value is in ('AES256', 'aws:kms', 'aws:kms:dsse', 'None')
                raise CloudknotInputError(
                    f"The server-side encryption option `sse` must be one of {valid_sse_names}. You provided {sse}."
                )
            if sse == "None":
                sse = None
        else:
            sse = None
        
        # Use set_s3_params to check for name availability
        # and write to config file
        bucket = bucket.replace("_", "-")  # S3 does not allow underscores
        set_s3_params(bucket=bucket, policy=policy, sse=sse)

        if policy is None:
            config.read(config_file)
            policy = config.get("aws", "s3-bucket-policy")

    # Get all local policies with cloudknot prefix
    paginator = clients.iam.get_paginator("list_policies")
    response_iterator = paginator.paginate(Scope="Local", PathPrefix="/cloudknot/")

    # response_iterator is a list of dicts. First convert to list of lists
    # and then flatten to a single list
    response_policies = [response["Policies"] for response in response_iterator]
    policies = [lst for sublist in response_policies for lst in sublist]
    
    try:
        aws_policies = {d["PolicyName"]: d["Arn"] for d in policies}
    except KeyError:
        raise CloudknotConfigurationError(f"All policiess in {policies} must have a 'PolicyName' and 'Arn' key.")

    return BucketInfo(bucket=bucket, policy=policy, policy_arn=aws_policies[policy], sse=cast(ServerSideEncryptionType, sse))


def set_s3_params(bucket: str, policy: Optional[str] = None, sse: Optional[ServerSideEncryptionType] = None):
    """Set the cloudknot S3 bucket.

    Set bucket by modifying the cloudknot config file

    Parameters
    ----------
    bucket : str
        Cloudknot S3 bucket name
    policy : str
        Cloudknot S3 bucket access policy name
        Default: None means that cloudknot will create a new policy
    sse : str
        S3 server side encryption method. If provided, must be one of
        ['AES256', 'aws:kms'].
        Default: None
    """
    if sse not in (valid_sse_names := get_args(ServerSideEncryptionType)): # Check if the sse value is in ('AES256', 'aws:kms', 'aws:kms:dsse', 'None')
        raise CloudknotInputError(
                        f"The server-side encryption option `sse` must be one of {valid_sse_names}. You provided {sse}."
                    )

    # Update the config file
    config_file = get_config_file()
    config = configparser.ConfigParser()
    
    bucket_call_args: dict[str, Any] = {"ServerSideEncryption": sse} if sse else {}
    def test_bucket_put_get(
        bucket_: str, sse_: Optional[ServerSideEncryptionType] = None
    ):
        
        key = "cloudnot-test-permissions-key"  # FIXME: Typo in word 'cloudnot'
        clients.s3.put_object(Bucket=bucket_, Key=key, Body=b"test", **bucket_call_args)
        clients.s3.get_object(Bucket=bucket_, Key=key, **bucket_call_args)

        except clients.s3.exceptions.ClientError as e:
            error_code = e.response["Error"]["Code"]
            
            mod_logger.debug(f"Got BucketAlreadyOwnedByYou exception for bucket {bucket}. Continuing.")
        except clients.s3.exceptions.BucketAlreadyExists:
            mod_logger.debug(f"Got BucketAlreadyExists exception for bucket {bucket}. Continuing with test_bucket_put_get().")
            test_bucket_put_get(bucket, sse)
        except clients.s3.exceptions.ClientError as e:
            # Check for Illegal Location Constraint
            error_code = e.response["Error"]["Code"]
            if error_code in {
                "IllegalLocationConstraintException",
                "InvalidLocationConstraint",
            }:
                response = clients.s3.get_bucket_location(Bucket=bucket)
                location = response.get("LocationConstraint")
                try:
                    if location == "us-east-1" or location is None:
                        clients.s3.create_bucket(Bucket=bucket)
                    else:
                        clients.s3.create_bucket(
                            Bucket=bucket,
                            CreateBucketConfiguration={"LocationConstraint": location},
                        )
                except clients.s3.exceptions.BucketAlreadyOwnedByYou:
                    pass
                except clients.s3.exceptions.BucketAlreadyExists:
                    test_bucket_put_get(bucket, sse)
            else:
                # Pass exception to user
                raise e
d `
        # Add the cloudknot tags to the bucket
        clients.s3.put_bucket_tagging(
            Bucket=bucket,
            Tagging={
                "TagSet": get_tags(
                    name=bucket,
                    additional_tags={"Project": "Cloudknot global config"},  # type: ignore
                )
            },
        )

        if policy is None:
            policy = "cloudknot-bucket-access-" + str(uuid.uuid4())

        try:
            # Create the policy
            s3_policy_doc = bucket_policy_document(bucket)

            clients.iam.create_policy(
                PolicyName=policy,
                Path="/cloudknot/",
                PolicyDocument=json.dumps(s3_policy_doc),
                Description="Grants access to S3 bucket {0:s}".format(bucket),
            )
        except clients.iam.exceptions.EntityAlreadyExistsException:
            # Policy already exists, do nothing
            pass

        config.set("aws", "s3-bucket-policy", policy)
        config.set("aws", "s3-sse", str(sse))
        with open(config_file, "w") as f:
            config.write(f)


def bucket_policy_document(
    bucket: str,
) -> dict[str, str | list[dict[str, str | list[str]]]]:
    """Return the policy document to access an S3 bucket.

    Parameters
    ----------
    bucket: str
        An Amazon S3 bucket name

    Returns
    -------
    s3_policy_doc: dict
        A dictionary containing the AWS policy document
    """
    # Add policy statements to access to cloudknot S3 bucket
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": ["s3:ListBucket"],
                "Resource": [f"arn:aws:s3:::{bucket}"],
            },
            {
                "Effect": "Allow",
                "Action": ["s3:PutObject", "s3:GetObject"],
                "Resource": [f"arn:aws:s3:::{bucket}/*"],
            },
        ],
    }


def update_s3_policy(policy: str, bucket: str):
    """Update the cloudknot S3 access policy with new bucket name.

    Parameters
    ----------
    policy: str
        Amazon S3 bucket access policy name.

    bucket: str
        Amazon S3 bucket name.
    """
    s3_policy_doc = bucket_policy_document(bucket)

    # Get all local policies with cloudknot prefix
    paginator = clients.iam.get_paginator("list_policies")
    response_iterator = paginator.paginate(Scope="Local", PathPrefix="/cloudknot/")

    # response_iterator is a list of dicts. First convert to list of lists
    # and then flatten to a single list
    response_policies = [response["Policies"] for response in response_iterator]
    policies = [lst for sublist in response_policies for lst in sublist]

    aws_policies = {d["PolicyName"]: d["Arn"] for d in policies}

    arn = aws_policies[policy]

    with rlock:
        try:
            # Update the policy
            clients.iam.create_policy_version(
                PolicyArn=arn,
                PolicyDocument=json.dumps(s3_policy_doc),
                SetAsDefault=True,
            )
        except clients.iam.exceptions.LimitExceededException:
            # Too many policy versions. List policy versions and delete oldest
            paginator = clients.iam.get_paginator("list_policy_versions")
            response_iterator = paginator.paginate(PolicyArn=arn)

            # Get non-default versions
            # response_iterator is a list of dicts. First convert to list of
            # lists. Then flatten to a single list and filter
            response_versions = [response["Versions"] for response in response_iterator]
            versions = [lst for sublist in response_versions for lst in sublist]
            versions = [v for v in versions if not v["IsDefaultVersion"]]

            # Get the oldest version and delete it
            oldest = sorted(versions, key=lambda ver: ver["CreateDate"])[0]
            clients.iam.delete_policy_version(
                PolicyArn=arn, VersionId=oldest["VersionId"]
            )

            # Update the policy not that there's room for another version
            clients.iam.create_policy_version(
                PolicyArn=arn,
                PolicyDocument=json.dumps(s3_policy_doc),
                SetAsDefault=True,
            )


def get_region() -> str:
    """Get the default AWS region.

    First, check the cloudknot config file for the region option.
    If that fails, check for the AWS_DEFAULT_REGION environment variable.
    If that fails, use the region in the AWS (not cloudknot) config file.
    If that fails, use us-east-1.

    Returns
    -------
    region : str
        default AWS region
    """
    config_file = get_config_file()
    config = configparser.ConfigParser()

    with rlock:
        config.read(config_file)

        if config.has_section("aws") and config.has_option("aws", "region"):
            return config.get("aws", "region")

        # Set `region`, the fallback region in case the cloudknot
        # config file has no region set

        try:
            # Get the region from an environment variable
            region = os.environ["AWS_DEFAULT_REGION"]
        except KeyError:
            # Get the default region from the AWS config file
            aws_config_file = os.path.expanduser(os.path.join("~", ".aws", "config"))

            fallback_region = "us-east-1"
            if os.path.isfile(aws_config_file):
                aws_config = configparser.ConfigParser()
                aws_config.read(aws_config_file)
                try:
                    region = aws_config.get(
                        "default", "region", fallback=fallback_region
                    )
                except TypeError:  # pragma: nocover
                    # python 2.7 compatibility
                    region = aws_config.get("default", "region")
                    region = region if region else fallback_region
            else:
                region = fallback_region

        if not config.has_section("aws"):
            config.add_section("aws")

        config.set("aws", "region", region)
        with open(config_file, "w") as f:
            config.write(f)

        return region


def set_region(region: str = "us-east-1"):
    """Set the AWS region that cloudknot will use.

    Set region by modifying the cloudknot config file and clients

    Parameters
    ----------
    region : str
        An AWS region.
        Default: 'us-east-1'
    """
    response = clients.ec2.describe_regions()
    region_names = [d["RegionName"] for d in response.get("Regions")]

    if region not in region_names:
        raise CloudknotInputError(
            "`region` must be in {regions!s}".format(regions=region_names)
        )

    config_file = get_config_file()
    config = configparser.ConfigParser()

    with rlock:
        config.read(config_file)

        if not config.has_section("aws"):  # pragma: nocover
            config.add_section("aws")

        config.set("aws", "region", region)
        with open(config_file, "w") as f:
            config.write(f)

        # Update the boto3 clients so that the region change is reflected
        # throughout the package
        clients.refresh(clients.iam.meta.config.max_pool_connections)

    mod_logger.debug("Set region to {region:s}".format(region=region))


class ProfileInfo(NamedTuple):
    """A NamedTuple with fields `profile_names`, `credentials_file`, and `aws_config_file`.

    profile_names :
        A list of AWS profiles in the aws config file and the aws shared credentials file

    credentials_file :
        A path to the aws shared credentials file

    aws_config_file :
        A path to the aws config file
    """

    profile_names: list[str]
    credentials_file: str
    aws_config_file: str


def list_profiles() -> ProfileInfo:
    """Return a list of available AWS profile names.

    Search the aws credentials file and the aws config file for profile names

    Returns
    -------
    :
        A NamedTuple with fields `profile_names`, a list of AWS profiles in
        the aws config file and the aws shared credentials file;
        `credentials_file`, a path to the aws shared credentials file;
        and `aws_config_file`, a path to the aws config file
    """
    aws = os.path.join(os.path.expanduser("~"), ".aws")

    try:
        # Get aws credentials file from environment variable
        env_file = os.environ["AWS_SHARED_CREDENTIALS_FILE"]
        credentials_file = os.path.abspath(env_file)
    except KeyError:
        # Fallback on default credentials file path
        credentials_file = os.path.join(aws, "credentials")

    try:
        # Get aws config file from environment variable
        env_file = os.environ["AWS_CONFIG_FILE"]
        aws_config_file = os.path.abspath(env_file)
    except KeyError:
        # Fallback on default aws config file path
        aws_config_file = os.path.join(aws, "config")

    credentials = configparser.ConfigParser()
    credentials.read(credentials_file)

    aws_config = configparser.ConfigParser()
    aws_config.read(aws_config_file)

    profile_names = [
        s.split()[1]
        for s in aws_config.sections()
        if s.split()[0] == "profile" and len(s.split()) == 2
    ]

    profile_names += credentials.sections()

    return ProfileInfo(
        profile_names=profile_names,
        credentials_file=credentials_file,
        aws_config_file=aws_config_file,
    )


def get_user() -> str:
    """Get the current AWS username."""
    user_info = clients.iam.get_user().get("User")
    return user_info.get("UserName", user_info.get("Arn").split(":")[-1])


def get_profile(fallback: Optional[str] = "from-env") -> str | None:
    """Get the AWS profile to use.

    First, check the cloudknot config file for the profile option.
    If that fails, check for the AWS_PROFILE environment variable.
    If that fails, return 'default' if there is a default profile in AWS config
    or credentials files. If that fails, return the fallback value.

    Parameters
    ----------
    fallback :
        The fallback value if get_profile() cannot find an AWS profile.
        Default: 'from-env'

    Returns
    -------
    profile_name :
        An AWS profile listed in the aws config file or aws shared
        credentials file
    """
    config_file = get_config_file()
    config = configparser.ConfigParser()

    with rlock:
        config.read(config_file)

        if config.has_section("aws") and config.has_option("aws", "profile"):
            return config.get("aws", "profile")

        # Set profile from environment variable
        try:
            profile = os.environ["AWS_PROFILE"]
        except KeyError:
            if "default" in list_profiles().profile_names:
                # Set profile in cloudknot config to 'default'
                profile = "default"
            else:
                return fallback

        if not config.has_section("aws"):
            config.add_section("aws")

        config.set("aws", "profile", profile)
        with open(config_file, "w") as f:
            config.write(f)

        return profile


def set_profile(profile_name: str):
    """Set the AWS profile that cloudknot will use.

    Set profile by modifying the cloudknot config file and clients

    Parameters
    ----------
    profile_name : str
        An AWS profile listed in the aws config file or aws shared
        credentials file
    """
    profile_info = list_profiles()

    if not (profile_name in profile_info.profile_names or profile_name == "from-env"):
        raise CloudknotInputError(
            "The profile you specified does not exist in either the AWS "
            "config file at {conf:s} or the AWS shared credentials file at "
            "{cred:s}.".format(
                conf=profile_info.aws_config_file, cred=profile_info.credentials_file
            )
        )

    config_file = get_config_file()
    config = configparser.ConfigParser()

    with rlock:
        config.read(config_file)

        if not config.has_section("aws"):  # pragma: nocover
            config.add_section("aws")

        config.set("aws", "profile", profile_name)
        with open(config_file, "w") as f:
            config.write(f)

        # Update the boto3 clients so that the profile change is reflected
        # throughout the package
        clients.refresh(clients.iam.meta.config.max_pool_connections)

    mod_logger.debug("Set profile to {profile:s}".format(profile=profile_name))


"""module-level dictionary of boto3 clients.

Storing the boto3 clients in a module-level dictionary allows us to change
the region and profile and have those changes reflected globally.

Advanced users: if you want to use cloudknot and boto3 at the same time,
you should use these clients to ensure that you have the right profile
and region.
"""

CLIENT_NAMES = ("batch", "cloudformation", "ecr", "ecs", "ec2", "iam", "s3")

c


def create_clients(
    max_pool: int = 10,
    CLIENT_NAMES=("batch", "cloudformation", "ecr", "ecs", "ec2", "iam", "s3"),
):
    """Refresh the boto3 clients dictionary."""
    config = botocore.config.Config(max_pool_connections=max_pool)
    return {  # type: ignore
        x: _make_client(x, config=config) for x in CLIENT_NAMES
    }


clients = create_clients()


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class ResourceExistsException(Exception):
    """Exception indicating that the requested AWS resource already exists."""

    def __init__(self, message: str, resource_id: str):
        """Initialize the Exception.

        Parameters
        ----------
        message : str
            The error message to display to the user

        resource_id : str
            The resource ID (e.g. ARN, VPC-ID) of the requested resource
        """
        super().__init__(message)
        self.resource_id = resource_id


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class ResourceDoesNotExistException(Exception):
    """Exception indicating that the requested AWS resource does not exists."""

    def __init__(self, message: str, resource_id: str):
        """Initialize the Exception.

        Parameters
        ----------
        message : str
            The error message to display to the user

        resource_id : str
            The resource ID (e.g. ARN, VPC-ID) of the requested resource
        """
        super().__init__(message)
        self.resource_id = resource_id


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class ResourceClobberedException(Exception):
    """Exception indicating that this AWS resource has been clobbered."""

    def __init__(self, message: str, resource_id: str):
        """Initialize the Exception.

        Parameters
        ----------
        message : str
            The error message to display to the user

        resource_id : str
            The resource ID (e.g. ARN, VPC-ID) of the requested resource
        """
        super().__init__(message)
        self.resource_id = resource_id


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class CannotDeleteResourceException(Exception):
    """Exception indicating that an AWS resource cannot be deleted."""

    def __init__(self, message, resource_id):
        """Initialize the Exception.

        Parameters
        ----------
        message : str
            The error message to display to the user

        resource_id : str
            The resource ID (e.g. ARN, VPC-ID) of the dependent resources
        """
        super().__init__(message)
        self.resource_id = resource_id


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class CannotCreateResourceException(Exception):
    """Exception indicating that an AWS resource cannot be created."""

    def __init__(self, message: str):
        """Initialize the Exception.

        Parameters
        ----------
        message : str
            The error message to display to the user
        """
        super().__init__(message)


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class CannotTagResourceException(Exception):
    """Exception indicating that an AWS resource cannot be tagged."""

    def __init__(self, message: str):
        """Initialize the Exception.

        Parameters
        ----------
        message : str
            The error message to display to the user
        """
        super().__init__(message)


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class RegionException(Exception):
    """Exception indicating the current region is not this resource's region."""

    def __init__(self, resource_region):
        """Initialize the Exception.

        Parameters
        ----------
        resource_region : str
            The resource region
        """
        super().__init__(
            "This resource's region ({resource:s}) does not match the "
            "current region ({current:s})".format(
                resource=resource_region, current=get_region()
            )
        )
        self.current_region = get_region()
        self.resource_region = resource_region


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class ProfileException(Exception):
    """Exception indicating the current profile isn't the resource's profile."""

    def __init__(self, resource_profile):
        """Initialize the Exception.

        Parameters
        ----------
        resource_profile : str
            The resource profile
        """
        super().__init__(
            "This resource's profile ({resource:s}) does not match the "
            "current profile ({current:s})".format(
                resource=resource_profile, current=get_profile()
            )
        )
        self.current_profile = get_profile()
        self.resource_profile = resource_profile


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class CKTimeoutError(Exception):
    """Cloudknot timeout error for AWS Batch job results.

    Error indicating an AWS Batch job failed to return results within
    the requested time period
    """

    def __init__(self, job_id):
        """Initialize the Exception."""
        super().__init__(
            "The job with job-id {jid:s} did not finish within the "
            "requested timeout period".format(jid=job_id)
        )
        self.job_id = job_id


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class BatchJobFailedError(Exception):
    """Error indicating an AWS Batch job failed."""

    def __init__(self, job_id: str):
        """Initialize the Exception.

        Parameters
        ----------
        job_id : str
            The AWS jobId of the failed job
        """
        super().__init__("AWS Batch job {job_id:s} has failed.".format(job_id=job_id))
        self.job_id = job_id


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class CloudknotConfigurationError(Exception):
    """Error indicating cloudknot has not been properly configured."""

    def __init__(self, config_file: str):
        """Initialize the Exception.

        Parameters
        ----------
        config_file : str
            The path to the cloudknot config file
        """
        super().__init__(
            "It looks like you haven't run `cloudknot configure` to set up "
            "your cloudknot environment. Or perhaps you did that but you have "
            "since deleted your cloudknot configuration file. Please run "
            "`cloudknot configure` before using cloudknot. "
        )
        self.config_file = config_file


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class CloudknotInputError(Exception):
    """Error indicating an input argument has an invalid value."""

    def __init__(self, msg: str):
        """Initialize the Exception.

        Parameters
        ----------
        msg : str
            The error message
        """
        super().__init__(msg)


# noinspection PyPropertyAccess,PyAttributeOutsideInit
class NamedObject(object):
    """Base class for building objects with name property."""

    def __init__(self, name: str):
        """Initialize a base class with a name.

        Parameters
        ----------
        name : str
            Name of the object.
            Must satisfy regular expression pattern: r'[a-zA-Z][-a-zA-Z0-9]*'
        """
        config_file = get_config_file()
        conf = configparser.ConfigParser()
        with rlock:
            conf.read(config_file)

            if not (
                conf.has_section("aws")
                and conf.has_option("aws", "configured")
                and conf.get("aws", "configured") == "True"
            ):
                raise CloudknotConfigurationError(config_file)

        pattern = re.compile(r"^[a-zA-Z][-a-zA-Z0-9]*$")
        if not pattern.match(name):
            raise CloudknotInputError(
                "We use name in AWS resource identifiers so it must "
                "satisfy the regular expression pattern: [a-zA-Z][-a-zA-Z0-9]*"
                " (note that underscores are not allowed)."
            )

        self._name = name
        self._clobbered = False
        self._region = get_region()
        self._profile = get_profile()

    @property
    def name(self):
        """The name of this AWS resource."""
        return self._name

    @property
    def clobbered(self):
        """Has this instance been previously clobbered."""
        return self._clobbered

    @property
    def region(self):
        """The AWS region in which this resource was created."""
        return self._region

    @property
    def profile(self):
        """The AWS profile in which this resource was created."""
        return self._profile

    def _get_section_name(self, resource_type: str) -> str:
        """Return the config section name.

        Append profile and region to the resource type name
        """
        return " ".join((resource_type, self.profile or "", self.region))

    def check_profile(self):
        """Check for profile exception."""
        if self.profile != get_profile():
            raise ProfileException(resource_profile=self.profile)

    def check_profile_and_region(self):
        """Check for region and profile exceptions."""
        if self.region != get_region():
            raise RegionException(resource_region=self.region)

        self.check_profile()
