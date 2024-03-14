###############################################################################
# Dockerfile to build application container
###############################################################################

ARG BASE_IMAGE=python:3
ARG PIP_ADD_OPTIONS=""
ARG REQUIREMENTS_PATH=/tmp/requirements.txt
ARG USERNAME=cloudknot-user
ARG SCRIPT_BASE_NAME

FROM ${BASE_IMAGE}

# Install python dependencies
RUN mkdir -p "$(dirname "${REQUIREMENTS_PATH}")"
COPY requirements.txt ""${REQUIREMENTS_PATH}"
RUN pip install --no-cache-dir ${PIP_ADD_OPTIONS} --requirement "${REQUIREMENTS_PATH}"

# Create a default user. Available via runtime flag `--user ${username}`.
# Add user to "staff" group.
RUN groupadd -f staff  \
    && useradd --create-home --groups staff "${USERNAME}"

# Copy the python script
COPY --chown="${USERNAME}" --chmod=775 "${SCRIPT_BASE_NAME}" "/home/${USERNAME}/"

# Set user
USER "${USERNAME}"

# Set working directory
WORKDIR "/home/${USERNAME}"

# Set entrypoint
ENTRYPOINT ["/home/${USERNAME}/${SCRIPT_BASE_NAME}"]
