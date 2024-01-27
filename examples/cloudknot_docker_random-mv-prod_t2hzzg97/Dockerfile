###############################################################################
# Dockerfile to build random-mv-prod application container
# Based on python:slim
###############################################################################

# Use official python base image
FROM python:slim

# Install python dependencies
COPY requirements.txt /tmp/
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Create a default user. Available via runtime flag `--user cloudknot-user`.
# Add user to "staff" group.
# Give user a home directory.

RUN useradd --create-home -g staff cloudknot-user || \
	echo "cloudknot-user already exists; skipping user creation." >&2

ENV HOME /home/cloudknot-user

# Set working directory
WORKDIR /home/cloudknot-user

# Set entrypoint
ENTRYPOINT ["python", "/home/cloudknot-user/random-mv-prod.py"]

# Copy the python script
COPY random-mv-prod.py /home/cloudknot-user/
