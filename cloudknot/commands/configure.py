import docker
import logging
import os
import subprocess
import configparser
import base64
# from awscli.customizations.configure.configure import InteractivePrompter

from .base import Base
from ..aws import (
    DockerRepo,
    get_profile,
    get_region,
    get_ecr_repo,
    set_profile,
    set_region,
    set_ecr_repo,
    list_profiles,
    clients
)
from ..config import add_resource

module_logger = logging.getLogger(__name__)
is_windows = os.name == "nt"


class InteractivePrompter(object):
    @staticmethod
    def mask_value(current_value):
        return None if current_value is None else "*" * 16 + current_value[-4:]
    
    def get_value(self, current_value, config_name, prompt_text=""):
        if config_name in ("aws_access_key_id", "aws_secret_access_key"):
            current_value = __class__.mask_value(current_value)
        response = input("%s [%s]: " % (prompt_text, current_value))
        if not response:
            # If the user hits enter, we return a value of None
            # instead of an empty string.  That way we can determine
            # whether or not a value has changed.
            response = None
        return response


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

    if profile != "from-env":
        cmd = [
            "aws",
            "ecr",
            "get-login",
            "--no-include-email",
            "--region",
            region,
            "--profile",
            profile,
        ]
    else:
        cmd = ["aws", "ecr", "get-login", "--no-include-email", "--region", region]

    ecr_client = clients["ecr"]
    response = ecr_client.get_authorization_token()

    username, password = (
        base64.b64decode(response["authorizationData"][0]["authorizationToken"])
        .decode()
        .split(":")
    )

    registry = response["authorizationData"][0]["proxyEndpoint"]

    cmd = f"docker login -u {username} -p {password} {registry}"

    # Refresh the aws ecr login credentials
    login_cmd = subprocess.check_output(cmd, shell=is_windows)

    # Login
    login_cmd = login_cmd.decode("ASCII").rstrip("\n").split(" ")
    fnull = open(os.devnull, "w")
    subprocess.call(login_cmd, stdout=fnull, stderr=subprocess.STDOUT, shell=is_windows)

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

    def run(self):
        print(
            "\n`cloudknot configure` is passing control over to "
            "`aws configure`. If you have already configured AWS "
            "CLI just press <ENTER> at the prompts to accept the pre-"
            "existing values. If you have not yet configured AWS CLI, "
            "please follow the prompts to start using cloudknot.\n"
        )

        # If you want to add new values to prompt, update this list here.

        profile = get_profile(fallback=os.environ.get("AWS_PROFILE", "default"))
        profiles = list_profiles()

        credentials = configparser.ConfigParser()
        credentials.read(profiles.credentials_file)
        values_to_prompt = [
            # (logical_name, config_name, prompt_text)
            ("aws_access_key_id", "AWS Access Key ID"),
            ("aws_secret_access_key", "AWS Secret Access Key"),
        ]

        for config_name, prompt_text in values_to_prompt:
            prompter = InteractivePrompter()
            new_value = prompter.get_value(
                current_value=credentials.get(profile, config_name, fallback=None),
                config_name=config_name,
                prompt_text=prompt_text,
            )

            if new_value is not None:
                if profile not in credentials:
                    credentials.add_section(profile)
                credentials.set(profile, config_name, new_value)
                with open(profiles.credentials_file, "w") as f:
                    credentials.write(f)

        config = configparser.ConfigParser()
        config.read(profiles.aws_config_file)
        if profile not in config:
            config.add_section(profile)
            with open(profiles.aws_config_file, "w") as f:
                config.write(f)
                config.read(profiles.aws_config_file)
        values_to_prompt = [
            # (logical_name, config_name, prompt_text)
            ("region", "Default region name"),
            ("output", "Default output format"),
        ]

        for config_name, prompt_text in values_to_prompt:
            prompter = InteractivePrompter()
            new_value = prompter.get_value(
                current_value=config.get(profile, config_name, fallback=None),
                config_name=config_name,
                prompt_text=prompt_text,
            )

            if new_value is not None:
                if profile not in config:
                    config.add_section(profile)
                config.set(profile, config_name, new_value)
                with open(profiles.aws_config_file, "w") as f:
                    config.write(f)

        # subprocess.call("aws configure".split(" "), shell=is_windows)

        print(
            "\naws configuration complete. Resuming configuration with "
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

        pull_and_push_base_images(
            region=values["region"],
            profile=values["profile"],
            ecr_repo=values["ecr_repo"],
        )

        print("All done.\n")
