# Use a specialized C++ dev container image
FROM mcr.microsoft.com/devcontainers/cpp:1-ubuntu-24.04

# Avoid prompts from apt
ENV DEBIAN_FRONTEND=noninteractive

# Add a non-root user for development
ARG USERNAME=devuser
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# The base image already has a user (usually 'vscode') with UID 1000.
# We rename it to the requested USERNAME to preserve existing setup.
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
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

# Install vcpkg if it doesn't exist.
# We check common locations and VCPKG_ROOT to avoid double installation.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libsqlite3-dev \
        libpq-dev \
        cmake \
        ninja-build \
        git \
        curl \
        zip \
        unzip \
        tar \
        pkg-config \
        ca-certificates \
    && if [ -z "$VCPKG_ROOT" ] && [ ! -d "/usr/local/vcpkg" ]; then \
        git clone --depth 1 https://github.com/microsoft/vcpkg.git /usr/local/vcpkg; \
        ACTUAL_VCPKG_ROOT=/usr/local/vcpkg; \
    elif [ -n "$VCPKG_ROOT" ]; then \
        ACTUAL_VCPKG_ROOT="$VCPKG_ROOT"; \
    else \
        ACTUAL_VCPKG_ROOT=/usr/local/vcpkg; \
    fi \
    && if [ ! -d "$ACTUAL_VCPKG_ROOT" ]; then echo "vcpkg not found at $ACTUAL_VCPKG_ROOT" && exit 1; fi \
    && if [ ! -x "$ACTUAL_VCPKG_ROOT/vcpkg" ] && [ -f "$ACTUAL_VCPKG_ROOT/bootstrap-vcpkg.sh" ]; then \
        "$ACTUAL_VCPKG_ROOT/bootstrap-vcpkg.sh" -disableMetrics; \
    fi \
    && chown -R $USERNAME:$USERNAME "$ACTUAL_VCPKG_ROOT" \
    && chmod -R u+rwX,go+rX "$ACTUAL_VCPKG_ROOT" \
    && if [ -f "$ACTUAL_VCPKG_ROOT/vcpkg" ]; then \
        chmod +x "$ACTUAL_VCPKG_ROOT/vcpkg"; \
    fi \
    && if [ "$ACTUAL_VCPKG_ROOT" != "/usr/local/vcpkg" ] && [ ! -e "/usr/local/vcpkg" ]; then \
        ln -s "$ACTUAL_VCPKG_ROOT" /usr/local/vcpkg; \
    fi \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/$USERNAME/.cache/vcpkg/archives /home/$USERNAME/.cache/vcpkg/downloads \
    && chown -R $USERNAME:$USERNAME /home/$USERNAME/.cache/vcpkg

USER $USERNAME
