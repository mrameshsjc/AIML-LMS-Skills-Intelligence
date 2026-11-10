// Jenkinsfile: the CI/CD pipeline for Jenkins (Phase 21). Guide: docs/JENKINS_CICD_GUIDE.md
//
// Stages (requirements, section 20):
//   1 Checkout                  2 Python environment        3 Dependencies
//   4 Code quality              5 Unit tests                6 API tests
//   7 Snyk dependency scan      8 Docker build (+ Snyk container scan)
//   9 Publish image (only if configured)                    10 Development deployment
//   11 Smoke test
//
// SECRETS: none in this file. They come from Jenkins credentials (Manage Jenkins -> Credentials):
//   snyk-token            Secret text      Snyk API token (stage 7/8; skipped with a warning if missing)
//   registry-credentials  Username/password container registry login (stage 9, only when publishing)
// The development deployment generates its own throw-away admin key on every build.
//
// Runs on a Linux agent with Python 3.11+, Docker CLI (talking to a Docker engine) and optionally
// the Snyk CLI: the Jenkins image in deployment/jenkins/ has all of them.

pipeline {
    agent any

    parameters {
        string(name: 'SNYK_SEVERITY', defaultValue: 'high', description: 'Lowest Snyk severity that counts: low, medium, high or critical')
        booleanParam(name: 'SNYK_FAIL_BUILD', defaultValue: false, description: 'Fail the build on Snyk findings (otherwise: UNSTABLE, yellow)')
        booleanParam(name: 'SNYK_MONITOR', defaultValue: false, description: 'Send a dependency snapshot to the Snyk dashboard for ongoing monitoring')
        booleanParam(name: 'PUBLISH_IMAGE', defaultValue: false, description: 'Push the image to a registry (needs REGISTRY_IMAGE and the registry-credentials credential)')
        string(name: 'REGISTRY_IMAGE', defaultValue: '', description: 'e.g. ghcr.io/<user>/aiml-lms-skills-intelligence or docker.io/<user>/aiml-lms-skills-intelligence')
        booleanParam(name: 'DEPLOY_DEV', defaultValue: true, description: 'Deploy the image as the development environment and smoke-test it')
    }

    options {
        timestamps()
        timeout(time: 60, unit: 'MINUTES')
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    environment {
        IMAGE = 'aiml-lms-skills-intelligence'
        IMAGE_TAG = "${env.BUILD_NUMBER}"
        VENV = "${env.WORKSPACE}/.venv"
        DEV_CONTAINER = 'lms-dev-api'
        DEV_NETWORK = 'lms-jenkins'           // the Docker network the Jenkins container is on (deployment/jenkins/compose.yaml)
        DEV_PORT = '18001'                     // development API on your PC: http://127.0.0.1:18001/docs
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
    }

    stages {
        stage('1. Checkout') {
            steps {
                checkout scm
                sh 'git log -1 --oneline'
            }
        }

        stage('2. Python environment') {
            steps {
                sh '''
                    python3 --version
                    python3 -m venv "$VENV"
                    "$VENV/bin/python" -m pip install --upgrade pip
                '''
            }
        }

        stage('3. Dependencies') {
            steps {
                sh '"$VENV/bin/python" -m pip install -r requirements-dev.txt'
            }
        }

        stage('4. Code quality') {
            steps {
                sh '''
                    "$VENV/bin/ruff" check .
                    "$VENV/bin/ruff" format --check .
                    if command -v kubectl >/dev/null; then
                        kubectl kustomize deployment/kubernetes > /dev/null && echo "Kubernetes manifests render"
                    else
                        echo "kubectl not installed on this agent: Kubernetes manifest check skipped"
                    fi
                '''
            }
        }

        stage('5. Unit tests') {
            steps {
                sh 'mkdir -p reports && "$VENV/bin/python" -m pytest tests/unit tests/security -q --junitxml=reports/junit-unit.xml'
            }
        }

        stage('6. API tests') {
            steps {
                // API, integration and dashboard tests, with the coverage report for app/
                sh '''
                    "$VENV/bin/python" -m pytest tests/api tests/integration tests/dashboard -q \
                        --junitxml=reports/junit-api.xml --cov=app --cov-report=xml:reports/coverage.xml --cov-report=term
                '''
            }
        }

        stage('7. Snyk dependency scan') {
            steps {
                script {
                    snyk('dependencies', """
                        snyk test --file=requirements.txt --package-manager=pip --command="$VENV/bin/python" \
                            --severity-threshold=${params.SNYK_SEVERITY} --json-file-output=reports/snyk-dependencies.json
                    """)
                    if (params.SNYK_MONITOR) {
                        snyk('monitor', 'snyk monitor --file=requirements.txt --package-manager=pip --command="$VENV/bin/python" --project-name=aiml-lms-skills-intelligence')
                    }
                }
            }
        }

        stage('8. Docker build') {
            steps {
                sh '''
                    docker build --build-arg APP_VERSION="$IMAGE_TAG" -t "$IMAGE:$IMAGE_TAG" -t "$IMAGE:dev-latest" .
                    test "$(docker run --rm --entrypoint id "$IMAGE:$IMAGE_TAG" -u)" = "10001"
                    echo "Image runs as user 10001 (not root)"
                    docker image ls "$IMAGE:$IMAGE_TAG" --format "Image size: {{.Size}}"
                '''
                script {
                    snyk('container', """
                        snyk container test "$IMAGE:$IMAGE_TAG" --file=Dockerfile --policy-path=.snyk \
                            --severity-threshold=${params.SNYK_SEVERITY} --json-file-output=reports/snyk-container.json
                    """)
                }
            }
        }

        stage('9. Publish image') {
            when { expression { params.PUBLISH_IMAGE && params.REGISTRY_IMAGE?.trim() } }
            steps {
                withCredentials([usernamePassword(credentialsId: 'registry-credentials',
                                                  usernameVariable: 'REGISTRY_USER', passwordVariable: 'REGISTRY_PASSWORD')]) {
                    sh '''
                        REGISTRY_HOST="${REGISTRY_IMAGE%%/*}"
                        echo "$REGISTRY_PASSWORD" | docker login "$REGISTRY_HOST" -u "$REGISTRY_USER" --password-stdin
                        docker tag "$IMAGE:$IMAGE_TAG" "$REGISTRY_IMAGE:$IMAGE_TAG"
                        docker tag "$IMAGE:$IMAGE_TAG" "$REGISTRY_IMAGE:latest"
                        docker push "$REGISTRY_IMAGE:$IMAGE_TAG"
                        docker push "$REGISTRY_IMAGE:latest"
                        docker logout "$REGISTRY_HOST"
                    '''
                }
            }
        }

        stage('10. Development deployment') {
            when { expression { params.DEPLOY_DEV } }
            steps {
                // Replace the previous development container with this build's image, hardened exactly
                // like compose.yaml (read-only, no capabilities, non-root). Its data volumes are kept.
                sh '''
                    set +x   # do not print the commands: they contain the admin key
                    DEV_ADMIN_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
                    echo "$DEV_ADMIN_KEY" > .dev-admin-key
                    docker rm -f "$DEV_CONTAINER" >/dev/null 2>&1 || true
                    docker run -d --name "$DEV_CONTAINER" --network "$DEV_NETWORK" -p "127.0.0.1:$DEV_PORT:8000" \
                        --read-only --tmpfs /tmp --tmpfs /home/appuser \
                        --cap-drop ALL --security-opt no-new-privileges:true \
                        -v lms-dev-db:/app/data/db -v lms-dev-index:/app/vector_store -v lms-dev-uploads:/app/data/uploads \
                        -v lms-dev-models:/app/models -v lms-dev-mlruns:/app/mlruns -v lms-dev-accounts:/app/data/accounts \
                        -v lms-dev-logs:/app/logs \
                        -e APP_PROFILE=compose -e DATA_SOURCE=database -e DATABASE_URL=sqlite:///./data/db/lms_ai.db \
                        -e ADMIN_API_KEY="$DEV_ADMIN_KEY" \
                        -e OLLAMA_BASE_URL=http://host.docker.internal:11434 --add-host host.docker.internal:host-gateway \
                        "$IMAGE:$IMAGE_TAG"
                    echo "Development API: http://127.0.0.1:$DEV_PORT/docs (on the Jenkins host)"
                '''
            }
        }

        stage('11. Smoke test') {
            when { expression { params.DEPLOY_DEV } }
            steps {
                sh '''
                    set +x   # the command line contains the admin key
                    echo "Smoke test of the development API (admin key from stage 10)"
                    "$VENV/bin/python" scripts/api_smoke_test.py --base-url "http://$DEV_CONTAINER:8000" --wait 120 \
                        --admin-key "$(cat .dev-admin-key)"
                '''
            }
        }
    }

    post {
        always {
            junit allowEmptyResults: true, testResults: 'reports/junit-*.xml'
            archiveArtifacts allowEmptyArchive: true, artifacts: 'reports/**'
            sh 'rm -f .dev-admin-key'
        }
        failure {
            sh 'docker logs --tail 80 "$DEV_CONTAINER" 2>&1 || true'
        }
        success {
            echo "Build ${env.BUILD_NUMBER} passed: image ${env.IMAGE}:${env.IMAGE_TAG}"
        }
    }
}

// Runs one Snyk command with the token from the 'snyk-token' credential.
// Snyk exit codes: 0 = nothing found, 1 = vulnerabilities found, 2 = error, 3 = no supported project.
// Findings fail the build only with SNYK_FAIL_BUILD; otherwise the build turns UNSTABLE (yellow),
// so a newly published vulnerability does not block everyday work, but nobody can miss it.
def snyk(String what, String command) {
    if (sh(script: 'command -v snyk', returnStatus: true) != 0) {
        unstable("Snyk ${what} scan skipped: the snyk CLI is not installed on this agent (see deployment/jenkins/).")
        return
    }
    try {
        withCredentials([string(credentialsId: 'snyk-token', variable: 'SNYK_TOKEN')]) {
            int rc = sh(script: command, returnStatus: true)
            if (rc == 1) {
                if (params.SNYK_FAIL_BUILD) {
                    error("Snyk ${what} scan found vulnerabilities at or above '${params.SNYK_SEVERITY}'.")
                }
                unstable("Snyk ${what} scan found vulnerabilities at or above '${params.SNYK_SEVERITY}' (see reports/).")
            } else if (rc >= 2) {
                unstable("Snyk ${what} scan could not run (exit code ${rc}); see the log above.")
            } else {
                echo "Snyk ${what} scan: no vulnerabilities at or above '${params.SNYK_SEVERITY}'."
            }
        }
    } catch (Exception e) {
        // A missing credential is a setup gap, not a failed build; anything else is re-thrown.
        if (!(e.message ?: '').contains("snyk-token")) {
            throw e
        }
        unstable("Snyk ${what} scan skipped: add the Secret text credential 'snyk-token' (docs/SNYK_SECURITY_GUIDE.md).")
    }
}
