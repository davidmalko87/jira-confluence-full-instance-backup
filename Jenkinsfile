// Atlassian weekly backup pipeline — cross-platform (Linux sh / Windows PowerShell).
// Stages are independent: Jira cookie expiry does NOT break the Confluence stage.
//
// Config comes from Jenkins GLOBAL env vars (set by the generated
// jenkins-setup.groovy) and is overridable per build via "Build with Parameters".
// Storage and notifications are pluggable; STORAGE_PROVIDER/STORAGE_DEST may be
// comma lists to upload to several backends at once.
//
// Secrets are bound via withCredentials and read by the Python modules from the
// environment — never interpolated into command strings.

def venvPython() { return isUnix() ? 'venv/bin/python' : 'venv\\Scripts\\python.exe' }

def runPy(String args) {
    if (isUnix()) {
        sh "${venvPython()} ${args}"
    } else {
        powershell "${venvPython()} ${args}"
    }
}

// Create the venv + install core and EACH selected provider's SDK (STORAGE_PROVIDER
// may be a comma list). Reads env.STORAGE_PROVIDER (set in the Setup preflight).
// The interpreter for the initial `venv` creation. Uses PYTHON_BIN if set
// (handy when the Jenkins service account's PATH lacks Python — set it to the
// full python.exe path), else auto-detects python3/python (Linux) or python/py
// (Windows). After the venv exists, its own python is used.
def setupVenv() {
    if (isUnix()) {
        sh '''
            set -e
            PY="$PYTHON_BIN"
            if [ -z "$PY" ]; then
                for c in python3 python; do command -v "$c" >/dev/null 2>&1 && PY="$c" && break; done
            fi
            PY="${PY:-python3}"
            echo "Using Python: $PY"
            "$PY" -m venv venv
            venv/bin/python -m pip install --quiet --upgrade pip
            venv/bin/python -m pip install --quiet -r requirements.txt
            for p in $(echo "$STORAGE_PROVIDER" | tr ',' ' '); do
                if [ -n "$p" ] && [ "$p" != "local" ]; then
                    venv/bin/python -m pip install --quiet -r "requirements-$p.txt"
                fi
            done
            mkdir -p "$OUT_DIR" "$ARCHIVE_DIR"
        '''
    } else {
        env.SEVEN_ZIP_PATH = 'C:\\Program Files\\7-Zip\\7z.exe'
        powershell '''
            $ErrorActionPreference = "Stop"
            $py = $env:PYTHON_BIN
            if (-not $py) {
                foreach ($cand in @('python','py')) {
                    if (Get-Command $cand -ErrorAction SilentlyContinue) { $py = $cand; break }
                }
            }
            if (-not $py) { $py = 'python' }
            Write-Host "Using Python: $py"
            & $py -m venv venv
            venv\\Scripts\\python.exe -m pip install --quiet --upgrade pip
            venv\\Scripts\\python.exe -m pip install --quiet -r requirements.txt
            foreach ($p in ($env:STORAGE_PROVIDER -split ',')) {
                $p = $p.Trim()
                if ($p -and $p -ne "local") {
                    venv\\Scripts\\python.exe -m pip install --quiet -r "requirements-$p.txt"
                }
            }
            New-Item -ItemType Directory -Force -Path $env:OUT_DIR | Out-Null
            New-Item -ItemType Directory -Force -Path $env:ARCHIVE_DIR | Out-Null
        '''
    }
}

pipeline {
    agent any

    triggers {
        // Schedule from the BACKUP_CRON global env var (set by the export), else default.
        cron("${env.BACKUP_CRON ?: 'H 2 * * 4'}")   // default: Thursday ~02:00
    }

    options {
        timeout(time: 2, unit: 'HOURS')
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '90'))
        disableConcurrentBuilds()
    }

    // Editable per run via "Build with Parameters"; defaults come from the global
    // env vars set by jenkins-setup.groovy.
    parameters {
        string(name: 'STORAGE_PROVIDER', defaultValue: "${env.STORAGE_PROVIDER ?: 'local'}",
               description: 'Backend(s), comma list: gcs,s3,azure,local')
        string(name: 'STORAGE_DEST', defaultValue: "${env.STORAGE_DEST ?: ''}",
               description: 'Destination(s), comma list aligned 1:1 with STORAGE_PROVIDER')
        string(name: 'S3_ENDPOINT_URL', defaultValue: "${env.S3_ENDPOINT_URL ?: ''}",
               description: 'S3-compatible endpoint (R2/B2/MinIO/Spaces); s3 only')
        string(name: 'NOTIFY_CHANNELS', defaultValue: "${env.NOTIFY_CHANNELS ?: ''}",
               description: 'Comma list: google-chat,slack,discord,teams,email,webhook (blank = none)')
        string(name: 'PRODUCT_NAME_TEMPLATE', defaultValue: "${env.PRODUCT_NAME_TEMPLATE ?: '{product}-{date}'}",
               description: 'Tokens: {product}{site}{date}{time}{datetime}{timestamp}')
        string(name: 'ARCHIVE_NAME_TEMPLATE', defaultValue: "${env.ARCHIVE_NAME_TEMPLATE ?: 'atlassian-backup-{date}'}",
               description: 'Archive (.7z) filename template')
        string(name: 'ARCHIVE_COMPRESSION', defaultValue: "${env.ARCHIVE_COMPRESSION ?: '5'}",
               description: '7-Zip compression: 0 (store) - 9 (ultra)')
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
                    // Sites come from global env (rarely change); fall back to placeholders.
                    env.SITE_JIRA       = env.SITE_JIRA       ?: 'https://<YOUR_SITE>.atlassian.net'
                    env.SITE_CONFLUENCE = env.SITE_CONFLUENCE ?: 'https://<YOUR_SITE>.atlassian.net/wiki'
                    // Run-time settings come from build parameters (whose defaults are
                    // the global env vars set by jenkins-setup.groovy).
                    env.STORAGE_PROVIDER      = params.STORAGE_PROVIDER
                    env.STORAGE_DEST          = params.STORAGE_DEST
                    env.S3_ENDPOINT_URL       = params.S3_ENDPOINT_URL
                    env.NOTIFY_CHANNELS       = params.NOTIFY_CHANNELS
                    env.PRODUCT_NAME_TEMPLATE = params.PRODUCT_NAME_TEMPLATE
                    env.ARCHIVE_NAME_TEMPLATE = params.ARCHIVE_NAME_TEMPLATE
                    env.ARCHIVE_COMPRESSION   = params.ARCHIVE_COMPRESSION
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
                    // STORAGE_PROVIDER may be a comma list -> bind the union of creds.
                    def providers = (env.STORAGE_PROVIDER ?: '').split(',').collect { it.trim() }.findAll { it }
                    def creds = []
                    if (providers.contains('gcs')) {
                        creds << file(credentialsId: 'gcp-backup-sa-key',
                                      variable: 'GOOGLE_APPLICATION_CREDENTIALS')
                    }
                    if (providers.contains('s3')) {
                        creds << string(credentialsId: 'aws-access-key-id',     variable: 'AWS_ACCESS_KEY_ID')
                        creds << string(credentialsId: 'aws-secret-access-key', variable: 'AWS_SECRET_ACCESS_KEY')
                    }
                    if (providers.contains('azure')) {
                        creds << string(credentialsId: 'azure-storage-connection-string',
                                        variable: 'AZURE_STORAGE_CONNECTION_STRING')
                    }
                    def extra = env.S3_ENDPOINT_URL?.trim() ? " --endpoint-url \"${env.S3_ENDPOINT_URL}\"" : ""
                    def cmd = "-m backup.upload --provider \"${env.STORAGE_PROVIDER}\" " +
                              "--dest \"${env.STORAGE_DEST}\"${extra}"
                    if (creds) {
                        withCredentials(creds) { runPy(cmd) }
                    } else {
                        runPy(cmd)   // local only — no credentials needed
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
