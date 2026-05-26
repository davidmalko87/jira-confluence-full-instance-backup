// Atlassian weekly backup pipeline — cross-platform (Linux sh / Windows PowerShell)
// Runs every Thursday ~02:00. Stages are independent: Jira cookie expiry does
// NOT break the Confluence stage.
//
// Storage and notifications are pluggable — set STORAGE_PROVIDER and
// NOTIFY_CHANNELS below; the pipeline installs the matching SDK and binds the
// matching credentials automatically.
//
// Secrets are bound via withCredentials and read by the Python modules from the
// environment — they are never interpolated into the command strings.

def venvPython() { return isUnix() ? 'venv/bin/python' : 'venv\\Scripts\\python.exe' }

// Run a backup.* module with the venv's Python, on either OS.
def runPy(String args) {
    if (isUnix()) {
        sh "${venvPython()} ${args}"
    } else {
        powershell "${venvPython()} ${args}"
    }
}

// Create the venv, install core + selected-provider deps, make work dirs.
def setupVenv() {
    if (isUnix()) {
        sh '''
            set -e
            python3 -m venv venv
            venv/bin/python -m pip install --quiet --upgrade pip
            venv/bin/python -m pip install --quiet -r requirements.txt
            if [ "$STORAGE_PROVIDER" != "local" ]; then
                venv/bin/python -m pip install --quiet -r "requirements-${STORAGE_PROVIDER}.txt"
            fi
            mkdir -p "$OUT_DIR" "$ARCHIVE_DIR"
        '''
    } else {
        // 7-Zip isn't on PATH for the Jenkins service by default on Windows.
        env.SEVEN_ZIP_PATH = 'C:\\Program Files\\7-Zip\\7z.exe'
        powershell '''
            $ErrorActionPreference = "Stop"
            python -m venv venv
            venv\\Scripts\\python.exe -m pip install --quiet --upgrade pip
            venv\\Scripts\\python.exe -m pip install --quiet -r requirements.txt
            if ($env:STORAGE_PROVIDER -ne "local") {
                venv\\Scripts\\python.exe -m pip install --quiet -r "requirements-$($env:STORAGE_PROVIDER).txt"
            }
            New-Item -ItemType Directory -Force -Path $env:OUT_DIR | Out-Null
            New-Item -ItemType Directory -Force -Path $env:ARCHIVE_DIR | Out-Null
        '''
    }
}

pipeline {
    agent any

    triggers {
        cron('H 2 * * 4')  // Thursday ~02:00
    }

    options {
        timeout(time: 2, unit: 'HOURS')
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '90'))
        disableConcurrentBuilds()
    }

    environment {
        OUT_DIR     = "${WORKSPACE}/out"
        ARCHIVE_DIR = "${WORKSPACE}/archive"
    }

    stages {

        stage('Setup') {
            steps {
                cleanWs()
                checkout scm
                script {
                    // Non-secret config. The generated jenkins-setup.groovy sets these
                    // as Jenkins GLOBAL env vars from your local .env; this block falls
                    // back to placeholders only when they're unset. For a manual setup,
                    // set them as global env vars (Manage Jenkins -> System) or edit here.
                    env.SITE_JIRA             = env.SITE_JIRA             ?: 'https://<YOUR_SITE>.atlassian.net'
                    env.SITE_CONFLUENCE       = env.SITE_CONFLUENCE       ?: 'https://<YOUR_SITE>.atlassian.net/wiki'
                    env.STORAGE_PROVIDER      = env.STORAGE_PROVIDER      ?: 'local'
                    env.STORAGE_DEST          = env.STORAGE_DEST          ?: '<YOUR_BUCKET>'
                    env.S3_ENDPOINT_URL       = env.S3_ENDPOINT_URL       ?: ''
                    env.NOTIFY_CHANNELS       = env.NOTIFY_CHANNELS       ?: ''
                    env.PRODUCT_NAME_TEMPLATE = env.PRODUCT_NAME_TEMPLATE ?: '{product}-{date}'
                    env.ARCHIVE_NAME_TEMPLATE = env.ARCHIVE_NAME_TEMPLATE ?: 'atlassian-backup-{date}'
                    env.ARCHIVE_COMPRESSION   = env.ARCHIVE_COMPRESSION   ?: '5'
                    echo "Config: jira=${env.SITE_JIRA} storage=${env.STORAGE_PROVIDER}:" +
                         "${env.STORAGE_DEST} notify=${env.NOTIFY_CHANNELS ?: '(none)'}"
                    setupVenv()
                }
            }
        }

        stage('Jira backup') {
            steps {
                withCredentials([
                    string(credentialsId: 'jira-cookies', variable: 'JIRA_COOKIES')
                ]) {
                    script { runPy("-m backup.jira --site \"${SITE_JIRA}\" --out \"${OUT_DIR}\"") }
                }
            }
        }

        stage('Confluence backup') {
            steps {
                withCredentials([
                    string(credentialsId: 'atlassian-email',     variable: 'ATL_EMAIL'),
                    string(credentialsId: 'atlassian-api-token', variable: 'ATL_TOKEN')
                ]) {
                    script { runPy("-m backup.confluence --site \"${SITE_CONFLUENCE}\" --out \"${OUT_DIR}\"") }
                }
            }
        }

        stage('Archive') {
            steps {
                withCredentials([
                    string(credentialsId: 'archive-password', variable: 'ARCHIVE_PASSWORD')
                ]) {
                    script { runPy("-m backup.archive --in \"${OUT_DIR}\" --out \"${ARCHIVE_DIR}\"") }
                }
            }
        }

        stage('Upload') {
            steps {
                script {
                    // Bind only the selected provider's credentials.
                    if (env.STORAGE_PROVIDER == 'gcs') {
                        withCredentials([file(credentialsId: 'gcp-backup-sa-key',
                                              variable: 'GOOGLE_APPLICATION_CREDENTIALS')]) {
                            runPy("-m backup.upload --provider gcs --dest \"${STORAGE_DEST}\" --in \"${ARCHIVE_DIR}\"")
                        }
                    } else if (env.STORAGE_PROVIDER == 's3') {
                        withCredentials([
                            string(credentialsId: 'aws-access-key-id',     variable: 'AWS_ACCESS_KEY_ID'),
                            string(credentialsId: 'aws-secret-access-key', variable: 'AWS_SECRET_ACCESS_KEY')
                        ]) {
                            def extra = env.S3_ENDPOINT_URL?.trim() ? " --endpoint-url \"${S3_ENDPOINT_URL}\"" : ""
                            runPy("-m backup.upload --provider s3 --dest \"${STORAGE_DEST}\" --in \"${ARCHIVE_DIR}\"${extra}")
                        }
                    } else if (env.STORAGE_PROVIDER == 'azure') {
                        withCredentials([string(credentialsId: 'azure-storage-connection-string',
                                                variable: 'AZURE_STORAGE_CONNECTION_STRING')]) {
                            runPy("-m backup.upload --provider azure --dest \"${STORAGE_DEST}\" --in \"${ARCHIVE_DIR}\"")
                        }
                    } else {  // local
                        runPy("-m backup.upload --provider local --dest \"${STORAGE_DEST}\" --in \"${ARCHIVE_DIR}\"")
                    }
                }
            }
        }
    }

    post {
        always {
            script {
                def status = currentBuild.currentResult == 'SUCCESS' ? 'success' : 'failure'
                def channels = (env.NOTIFY_CHANNELS ?: '').split(',').collect { it.trim() }
                def needsWebhook = channels.any { it in ['google-chat', 'slack', 'discord', 'teams', 'webhook'] }
                def needsEmail = channels.contains('email')

                def creds = []
                if (needsWebhook) {
                    creds << string(credentialsId: 'notify-webhook-url', variable: 'NOTIFY_WEBHOOK_URL')
                }
                if (needsEmail) {
                    creds << string(credentialsId: 'smtp-host',     variable: 'SMTP_HOST')
                    creds << string(credentialsId: 'smtp-from',     variable: 'SMTP_FROM')
                    creds << string(credentialsId: 'smtp-to',       variable: 'SMTP_TO')
                    creds << string(credentialsId: 'smtp-user',     variable: 'SMTP_USER')
                    creds << string(credentialsId: 'smtp-password', variable: 'SMTP_PASSWORD')
                }

                if (creds) {
                    withCredentials(creds) {
                        try {
                            runPy("-m backup.notify --channels \"${env.NOTIFY_CHANNELS}\" " +
                                  "--status ${status} --archive-dir \"${env.ARCHIVE_DIR}\" " +
                                  "--build-url \"${env.BUILD_URL}\"")
                        } catch (ignored) {
                            echo "notify failed (non-fatal)"
                        }
                    }
                }
            }
            cleanWs()
        }
    }
}
