###############################################################################
# Dockerfile to build unit-testing-func application container
# Based on python:3
###############################################################################

# Use official python base image
FROM python:3

# Install python dependencies from requirements.txt if it exists
COPY requirements.tx[t] /tmp/
RUN ( test -f "/tmp/requirements.txt" && echo 1 && pip install --no-cache-dir -r "/tmp/requirements.txt" ) || echo "No requirements.txt file found"

# Create a default user. Available via runtime flag `--user cloudknot-user`.
# Create a staff group if it does not exist.
# Create a user, add them to the staff group, and create their home directory.
RUN groupadd -f staff && useradd --create-home --groups staff "cloudknot-user"

# Copy the python script
COPY --chown=cloudknot-user "unit-testing-func.py" "/home/cloudknot-user/"

# Set the user to use when running this image
USER "cloudknot-user"

# Set working directory
WORKDIR "/home/cloudknot-user"

# Set entrypoint
ENTRYPOINT ["python", "/home/cloudknot-user/unit-testing-func.py"]
