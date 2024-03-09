import docker
import logging
import os
import configparser
from .base import Base
from ..aws import (
    DockerRepo,
    get_profile,
    get_region,
    get_ecr_repo,
    set_profile,
    set_region,
    set_ecr_repo,
    refresh_clients,
    clients,
    list_profiles,
)
from ..config import add_resource, rlock
from base64 import b64decode
import botocore

module_logger = logging.getLogger(__name__)
is_windows = os.name == "nt"


def pull_and_push_base_images(region, profile, ecr_repo):
    # Use docker low-level APIClient for tagging
    c = docker.from_env().api
    # And the image client for pulling and pushing
    cli = docker.from_env().images

    # Build the python base image so that later build commands are faster
    py_base = "python:3"
    ecr_tag = "python3"
    module_logger.info("Pulling base image {b:s}".format(b=py_base))
    cli.pull(py_base)

    # Refresh the aws ecr login credentials
    refresh_clients()

    try:
        response = clients["ecr"].get_authorization_token()
    except botocore.exceptions.ClientError as e:
        raise RuntimeError(
            "Could not get ECR authorization token to log in to the Docker registry"
        ) from e

    username, password = (
        b64decode(response["authorizationData"][0]["authorizationToken"])
        .decode()
        .split(":")
    )
    registry = response["authorizationData"][0]["proxyEndpoint"]

    try:
        # Log in to the Docker registry using the AWS ECR token
        c.login(username, password, registry=registry)
    except docker.errors.DockerException as e:
        raise RuntimeError(f"Could not log in to the Docker registry {registry}") from e

    repo = DockerRepo(name=ecr_repo)

    # Log tagging info
    module_logger.info("Tagging base image {name:s}".format(name=py_base))

    # Tag it with the most recently added image_name
    c.tag(image=py_base, repository=repo.repo_uri, tag=ecr_tag)

    # Log push info
    module_logger.info(
        "Pushing base image {name:s} to ecr repository {repo:s}"
        "".format(name=py_base, repo=repo.repo_uri)
    )

    for line in cli.push(repository=repo.repo_uri, tag=ecr_tag, stream=True):
        module_logger.debug(line)


class Configure(Base):
    """Run `aws configure` and set up cloudknot AWS ECR repository"""

    @staticmethod
    def _interactive_prompt(current_value, config_name, prompt_text=""):
        """Prompt the user for a value, masking the current value if it exists"""
        if (
            config_name in ("aws_access_key_id", "aws_secret_access_key")
            and current_value is not None
        ):
            current_value = "*" * 16 + current_value[-4:]
        response = input("%s [%s]: " % (prompt_text, current_value))
        return None if not response else response

    def run(self):
        print(
            "\n`cloudknot configure` is passing control over to "
            "`aws configure`. If you have already configured AWS "
            "CLI just press <ENTER> at the prompts to accept the pre-"
            "existing values. If you have not yet configured AWS CLI, "
            "please follow the prompts to start using cloudknot.\n"
            "\n`cloudknot configure` will try to set up credentials for AWS."
            "If you have already configured credentials for AWS, just press"
            "<ENTER> at the prompts to accept the pre-existing values.\n"
        )

        print(
            "\nAWS credential configuration complete. Resuming configuration with "
            "`cloudknot configure`\n"
        )

        with rlock:
            profile = get_profile(fallback="default")
            profiles = list_profiles()

            # Set up AWS configuration like `aws configure` from awscli:

            # Set up credentials config (default in ~/.aws/credentials):
            credentials_config = configparser.ConfigParser()
            credentials_config.read(profiles.credentials_file)
            updated_credentials = False  # Flag to refresh if credentials updated

            # Prompt for AWS credentials to set up or update:
            for config_name, prompt_text in (
                ("aws_access_key_id", "AWS Access Key ID"),
                ("aws_secret_access_key", "AWS Secret Access Key"),
            ):
                new_value = self._interactive_prompt(
                    current_value=credentials_config.get(
                        profile, config_name, fallback=None
                    ),
                    config_name=config_name,
                    prompt_text=prompt_text,
                )
                if new_value is not None:
                    if profile not in credentials_config:
                        credentials_config.add_section(profile)
                    credentials_config.set(profile, config_name, new_value)
                    # Write the updated credentials back to the file:
                    with open(profiles.credentials_file, "w") as f:
                        credentials_config.write(f)
                        updated_credentials = True

        # Set up aws config (default in ~/.aws/config):
        aws_config = configparser.ConfigParser(default_section="default")
        aws_config.read(profiles.aws_config_file)

        # Prompt for default region name to set up or update:
        for config_name, prompt_text in (("region", "Default region name"),):
            new_value = self._interactive_prompt(
                current_value=aws_config.get(profile, config_name, fallback=None),
                config_name=config_name,
                prompt_text=prompt_text,
            )
            if new_value is not None:
                aws_config.set("default", config_name, new_value)
                # Write the updated aws config back to the file:
                with open(profiles.aws_config_file, "w") as f:
                    aws_config.write(f)

        # Create an empty aws config file if it doesn't exist:
        if not os.path.exists(profiles.aws_config_file):
            with open(profiles.aws_config_file, "w") as f:
                f.writelines("[default]")

        # Refresh the clients if the credentials were updated:
        if updated_credentials:
            refresh_clients()

        # Proceed with the cloudknot-specific configuration:
        values_to_prompt = (
            # (config_name, prompt_text, getter, setter)
            ("profile", "AWS profile to use", get_profile, set_profile),
            ("region", "Default region name", get_region, set_region),
            ("ecr_repo", "Default AWS ECR repository name", get_ecr_repo, set_ecr_repo),
        )

        values = {}
        for config_name, prompt_text, getter, setter in values_to_prompt:
            default_value = getter()

            new_value = self._interactive_prompt(
                current_value=default_value,
                config_name=config_name,
                prompt_text=prompt_text,
            )

            if new_value is not None and new_value != default_value:
                values[config_name] = new_value
                setter(new_value)
            else:
                values[config_name] = default_value

        add_resource("aws", "configured", "True")

        print(
            "\nCloudknot will now pull the base python docker image to your "
            "local machine and push the same docker image to your cloudknot "
            "repository on AWS ECR."
        )

        pull_and_push_base_images(
            region=values["region"],
            profile=values["profile"],
            ecr_repo=values["ecr_repo"],
        )

        print("All done.\n")
