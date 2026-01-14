# Use an official Ubuntu as a parent image
FROM ubuntu:24.04

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# Install essential build tools and dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    gdb \
    clang \
    git \
    python3 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Add a non-root user for development
ARG USERNAME=devuser
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# In Ubuntu 24.04, the 'ubuntu' user already exists with UID/GID 1000.
# We check if the group/user exists before creating them, or just use them if they match.
RUN if getent group $USER_GID; then \
        EXISTING_GROUP=$(getent group $USER_GID | cut -d: -f1); \
        if [ "$EXISTING_GROUP" != "$USERNAME" ]; then \
            groupmod --new-name $USERNAME $EXISTING_GROUP; \
        fi; \
    else \
        groupadd --gid $USER_GID $USERNAME; \
    fi \
    && if getent passwd $USER_UID; then \
        EXISTING_USER=$(getent passwd $USER_UID | cut -d: -f1); \
        if [ "$EXISTING_USER" != "$USERNAME" ]; then \
            usermod --login $USERNAME --move-home --home /home/$USERNAME $EXISTING_USER; \
        fi; \
    else \
        useradd --uid $USER_UID --gid $USER_GID -m $USERNAME; \
    fi \
    && apt-get update \
    && apt-get install -y sudo \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

USER $USERNAME
