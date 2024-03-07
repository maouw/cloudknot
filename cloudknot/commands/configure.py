import base64
import configparser
import logging
import os

import docker

from ..aws import (
    DockerRepo,
    clients,
    get_ecr_repo,
    get_profile,
    get_region,
    list_profiles,
    refresh_clients,
    set_ecr_repo,
    set_profile,
    set_region,
)
from ..config import add_resource, rlock
from .base import Base

module_logger = logging.getLogger(__name__)
is_windows = os.name == "nt"


def pull_and_push_base_images(region, profile, ecr_repo):  # noqa: ARG001 # FIXME: Parameters profile and region are not used -- remove?
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

    response = clients["ecr"].get_authorization_token()
    username, password = (
        base64.b64decode(response["authorizationData"][0]["authorizationToken"])
        .decode()
        .split(":")
    )
    registry = response["authorizationData"][0]["proxyEndpoint"]

    # Login
    c.login(username, password, registry=registry)

    repo = DockerRepo(name=ecr_repo)

    # Log tagging info
    module_logger.info("Tagging base image {name:s}".format(name=py_base))

    # Tag it with the most recently added image_name
    c.tag(image=py_base, repository=repo.repo_uri, tag=ecr_tag)

    # Log push info
    module_logger.info(
        "Pushing base image {name:s} to ecr repository {repo:s}" "".format(
            name=py_base, repo=repo.repo_uri
        )
    )

    for line in cli.push(repository=repo.repo_uri, tag=ecr_tag, stream=True):
        module_logger.debug(line)


class Configure(Base):
    """Run `aws configure` and set up cloudknot AWS ECR repository"""

    @staticmethod
    def interactive_prompt(current_value, config_name, prompt_text=""):
        if (
            config_name in q("aws_access_key_id", "aws_secret_access_key")
            and current_value
        ):
            current_value = "*" * 16 + current_value[-4:]
        response = input("%s [%s]: " % (prompt_text, current_value))
        if not response:
            # If the user hits enter, we return a value of None
            # instead of an empty string.  That way we can determine
            # whether or not a value has changed.
            response = None
        return response

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

            credentials_config = configparser.ConfigParser()
            if os.path.exists(profiles.credentials_file):
                credentials_config.read(profiles.credentials_file)

            updated_credentials = False
            for config_name, prompt_text in (
                ("aws_access_key_id", "AWS Access Key ID"),
                ("aws_secret_access_key", "AWS Secret Access Key"),
            ):
                new_value = self.interactive_prompt(
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
                    with open(profiles.credentials_file, "w") as f:
                        credentials_config.write(f)
                    updated_credentials = True
        if updated_credentials:
            refresh_clients()

        values_to_prompt = [
            # (config_name, prompt_text, getter, setter)
            ("profile", "AWS profile to use", get_profile, set_profile),
            ("region", "Default region name", get_region, set_region),
            ("ecr_repo", "Default AWS ECR repository name", get_ecr_repo, set_ecr_repo),
        ]

        values = {}
        for config_name, prompt_text, getter, setter in values_to_prompt:
            default_value = getter()

            new_value = self.interactive_prompt(
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
