###############################################################################
# Dockerfile to build ${app_name} application container
# Based on ${base_image}
###############################################################################

# Use official python base image
FROM ${base_image}

# Install python dependencies
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt${github_installs_string}

# Create a default user. Available via runtime flag `--user ${username}`.
# Add user to "staff" group.
# Give user a home directory.

RUN useradd --create-home -g staff cloudknot-user || \
	echo "cloudknot-user already exists; skipping user creation." >&2

ENV HOME /home/${username}

# Set working directory
WORKDIR /home/${username}

# Set entrypoint
ENTRYPOINT ["python", "/home/${username}/${script_base_name}"]

# Copy the python script
COPY ${script_base_name} /home/${username}/
