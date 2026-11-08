# Jenkins for this project (Phase 21): the official Jenkins LTS image plus the tools the Jenkinsfile uses.
#   Python 3 + venv    stages 2-6 and the smoke test
#   Docker CLI         stages 8-10 (official static binary): builds and runs containers on the Docker engine of your PC
#                      (Docker Desktop), reached through the mounted /var/run/docker.sock
#   kubectl            stage 4 renders the Kubernetes manifests
#   Snyk CLI           stages 7-8 (the token comes from a Jenkins credential, never from here)
# Started by compose.yaml in this folder. Guide: docs/JENKINS_CICD_GUIDE.md
#
# The LTS tag moves with each release; pin it (e.g. jenkins/jenkins:2.xxx.x-lts-jdk21) for repeatable builds.
FROM jenkins/jenkins:lts-jdk21

ARG KUBECTL_VERSION=v1.31.4
# Docker's official standalone CLI: the same on every Debian release (the docker.io package of
# newer Debian releases no longer ships the docker command itself).
ARG DOCKER_CLI_VERSION=27.5.1

USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv python3-pip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ARCH="$(dpkg --print-architecture)" \
    && case "$ARCH" in arm64) DOCKER_ARCH=aarch64; SNYK=snyk-linux-arm64 ;; *) DOCKER_ARCH=x86_64; SNYK=snyk-linux ;; esac \
    && curl -fsSL "https://download.docker.com/linux/static/stable/${DOCKER_ARCH}/docker-${DOCKER_CLI_VERSION}.tgz" \
       | tar -xz -C /usr/local/bin --strip-components=1 docker/docker \
    && curl -fsSLo /usr/local/bin/kubectl "https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/${ARCH}/kubectl" \
    && curl -fsSLo /usr/local/bin/snyk "https://static.snyk.io/cli/latest/${SNYK}" \
    && chmod +x /usr/local/bin/docker /usr/local/bin/kubectl /usr/local/bin/snyk
# One check per tool: if a tool is missing, the failing build step names it
RUN python3 --version
RUN docker --version
RUN kubectl version --client
RUN snyk --version
USER jenkins

# The plugins the Jenkinsfile needs (most come with "Install suggested plugins" anyway).
RUN jenkins-plugin-cli --plugins workflow-aggregator git credentials-binding timestamper junit
