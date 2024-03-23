"""Process pip GitHub requirements."""

from urllib.parse import urlparse

from packaging.requirements import InvalidRequirement, Requirement

from .aws.base_classes import (
    CloudknotInputError,
)

__all__ = ["parse_github_requirement"]


class GitHubRequirement:
    valid_schemes = (
        "git+http",
        "git+https",
        "git+ssh",
    )

    valid_netlocs = ("github.com",)

    def __init__(self, spec: str):
        self.original_spec = spec
        url = spec.strip()
        if not url:
            raise CloudknotInputError("URL cannot be empty.")

        url_components = urlparse(url)

        match url_components.scheme:
            case "git" | "ssh" | "git+ssh" | "git+http":
                url_components = url_components._replace(scheme="git+https")
            case "http" | "https":
                url_components = url_components._replace(
                    scheme="git+" + url_components.scheme
                )

        if url_components.scheme not in self.valid_schemes:
            raise CloudknotInputError(
                f'Invalid scheme {url_components.scheme} in URL: "{self.original_spec}". Scheme must be one of {self.valid_schemes}.'
            )

        if url_components.netloc not in self.valid_netlocs:
            raise CloudknotInputError(
                f'Invalid netloc {url_components.netloc} in URL: "{self.original_spec}". Netloc must be one of {self.valid_netlocs}.'
            )

        self.url = url_components.geturl()
        self.spec = self.url

    def __str__(self) -> str:
        return str(self.spec)

    def __repr__(self) -> str:
        return f'{__class__.__name__}("{self.spec}")'


class GitHubNameSpecRequirement(GitHubRequirement):
    def __init__(self, spec: str):
        try:
            requirement = Requirement(spec)
        except InvalidRequirement as e:
            raise ValueError(
                f'Invalid package requirement specification: "{spec}". Please visit https://pip.pypa.io/en/latest/topics/vcs-support for more information.'
            ) from e
        super().__init__(requirement.url)
        requirement.url = self.url
        self.spec = str(requirement)


def parse_github_requirement(url: str) -> str:
    """Parse a GitHub URL into a pip requirement."""
    try:
        requirement = GitHubRequirement(url)
    except CloudknotInputError:
        try:
            requirement = GitHubNameSpecRequirement(url)
        except ValueError as e:
            raise CloudknotInputError(
                f'Invalid GitHub URL or package requirement specification: "{url}". Please visit https://pip.pypa.io/en/latest/topics/vcs-support for more information.'
            ) from e
    return str(requirement)
