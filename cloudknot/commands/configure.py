import logging
import os
import subprocess
from base64 import b64decode

import botocore.exceptions
import docker
import docker.errors
from awscli.customizations.configure.configure import InteractivePrompter

from ..aws import (
    DockerRepo,
    clients,
    get_ecr_repo,
    get_profile,
    get_region,
    refresh_clients,
    set_ecr_repo,
    set_profile,
    set_region,
)
from ..config import add_resource
from .base import Base

module_logger = logging.getLogger(__name__)


def pull_and_push_base_images(ecr_repo):
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
        "Pushing base image {name:s} to ecr repository {repo:s}".format(
            name=py_base, repo=repo.repo_uri
        )
    )

    for line in cli.push(repository=repo.repo_uri, tag=ecr_tag, stream=True):
        module_logger.debug(line)


class Configure(Base):
    """Run `aws configure` and set up cloudknot AWS ECR repository"""

    def run(self):
        print(
            "\n`cloudknot configure` is passing control over to "
            "`aws configure`. If you have already configured AWS "
            "CLI just press <ENTER> at the prompts to accept the pre-"
            "existing values. If you have not yet configured AWS CLI, "
            "please follow the prompts to start using cloudknot.\n"
        )

        subprocess.call("aws configure".split(" "), shell=(os.name == "nt"))

        print(
            "\n`aws configure` complete. Resuming configuration with "
            "`cloudknot configure`\n"
        )

        values_to_prompt = [
            # (config_name, prompt_text, getter, setter)
            ("profile", "AWS profile to use", get_profile, set_profile),
            ("region", "Default region name", get_region, set_region),
            ("ecr_repo", "Default AWS ECR repository name", get_ecr_repo, set_ecr_repo),
        ]

        values = {}
        for config_name, prompt_text, getter, setter in values_to_prompt:
            prompter = InteractivePrompter()
            default_value = getter()

            new_value = prompter.get_value(
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
        refresh_clients()

        pull_and_push_base_images(
            region=values["region"],
            profile=values["profile"],
            ecr_repo=values["ecr_repo"],
        )

        print("All done.\n")
