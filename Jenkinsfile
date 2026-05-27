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

// Send notifications. Binds jira-cookies too so backup.notify can warn when the
// session cookie is near expiry. Never fails the build.
def runNotify(String status) {
    def channels = (env.NOTIFY_CHANNELS ?: '').split(',').collect { it.trim() }.findAll { it }
    def needsWebhook = channels.any { it in ['google-chat', 'slack', 'discord', 'teams', 'webhook'] }
    def needsEmail = channels.contains('email')
    if (!needsWebhook && !needsEmail) {
        echo "No notification channels configured — skipping notify."
        return
    }
    def creds = [string(credentialsId: 'jira-cookies', variable: 'JIRA_COOKIES')]
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
    try {
        withCredentials(creds) {
            runPy("-m backup.notify --channels \"${env.NOTIFY_CHANNELS}\" " +
                  "--status ${status.toLowerCase()} --archive-dir \"${env.ARCHIVE_DIR}\" " +
                  "--build-url \"${env.BUILD_URL}\"")
        }
    } catch (err) {
        echo "notify failed (non-fatal): ${err.message}"
    }
}

// True when at least one product backup (.zip) landed in OUT_DIR. Lets the
// pipeline archive + upload whatever succeeded even if a product stage failed
// or was skipped — a cooldown marker alone does NOT count as a backup.
def hasBackups() {
    def py = "import glob,os,sys; sys.exit(0 if glob.glob(os.path.join(os.environ['OUT_DIR'], '*.zip')) else 1)"
    if (isUnix()) {
        return sh(returnStatus: true, script: "${venvPython()} -c \"${py}\"") == 0
    }
    return powershell(returnStatus: true, script: "${venvPython()} -c \"${py}\"") == 0
}

// Run a backup module and return its exit code (no exception on non-zero).
def runStatus(String cmd) {
    if (isUnix()) {
        return sh(returnStatus: true, script: "${venvPython()} ${cmd}")
    }
    return powershell(returnStatus: true, script: "${venvPython()} ${cmd}")
}

// ───────────────────────── Failure policy ─────────────────────────
// Map a stage OUTCOME to an ACTION under the chosen FAILURE_POLICY preset.
//   outcomes : success | cooldown | credentials | error | nobackup | upload
//   actions  : 'ok' (continue) | 'unstable' (continue + mark UNSTABLE) | 'abort' (fail now)
//
//   strict    : anything that isn't a clean success aborts the build.
//   resilient : never aborts — every problem only marks the build UNSTABLE.
//   balanced  : (default) hard-fail on credentials / error / nobackup; soft
//               (unstable + continue) on cooldown and upload-target failures.
//
// FULL CONTROL: each outcome also has a per-outcome override parameter
// (ON_COOLDOWN, ON_CREDENTIALS, ON_BACKUP_ERROR, ON_NO_BACKUP, ON_UPLOAD_FAILURE).
// Left at 'default' it follows the preset above; set to continue/unstable/abort
// to override that single outcome regardless of the preset.
def policyFor(String outcome) {
    if (outcome == 'success') { return 'ok' }

    // First: a per-outcome override wins when set to something other than 'default'.
    def override = [
        cooldown:    params.ON_COOLDOWN,
        credentials: params.ON_CREDENTIALS,
        error:       params.ON_BACKUP_ERROR,
        nobackup:    params.ON_NO_BACKUP,
        upload:      params.ON_UPLOAD_FAILURE,
    ].get(outcome)
    if (override && override != 'default') {
        return (override == 'continue') ? 'ok' : override   // 'unstable' / 'abort' pass through
    }

    // Otherwise: fall back to the FAILURE_POLICY preset.
    def preset = params.FAILURE_POLICY ?: 'balanced'
    if (preset == 'resilient') { return 'unstable' }
    if (preset == 'strict')    { return 'abort' }
    // balanced
    if (outcome == 'cooldown' || outcome == 'upload') { return 'unstable' }
    return 'abort'   // credentials, error, nobackup
}

// Classify a backup module's exit code, then apply the failure policy.
//   exit 0 = success · 2 = credentials · 3 = cooldown/no-backup · else = error
def runBackup(String product, String cmd) {
    int code = runStatus(cmd)
    def outcome = [0: 'success', 2: 'credentials', 3: 'cooldown'].get(code, 'error')
    def preset = params.FAILURE_POLICY ?: 'balanced'
    def action = policyFor(outcome)
    echo "[${product}] exit=${code} outcome=${outcome} policy=${preset} -> ${action}"
    if (action == 'abort') {
        error("${product} backup: ${outcome} (exit ${code}) — stopping per '${preset}' policy")
    } else if (action == 'unstable') {
        unstable("${product} backup: ${outcome} (exit ${code}) — continuing; build marked UNSTABLE")
    }
}

pipeline {
    agent any

    triggers {
        // Schedule from the BACKUP_CRON global env var (set by the export), else default.
        cron("${env.BACKUP_CRON ?: 'H 2 * * 4'}")   // default: Thursday ~02:00
    }

    options {
        // Jira/Confluence exports can take from minutes to several hours; this is the
        // hard wall-clock cap for the whole build (backup + archive + upload). The
        // per-backup poll wait is governed separately by POLL_TIMEOUT (see parameters).
        timeout(time: 8, unit: 'HOURS')
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '90'))
        disableConcurrentBuilds()
    }

    // Editable per run via "Build with Parameters"; defaults come from the global
    // env vars set by jenkins-setup.groovy.
    parameters {
        // --- Failure policy: how the pipeline reacts to each outcome ---
        choice(name: 'FAILURE_POLICY',
               choices: ([(env.FAILURE_POLICY ?: 'balanced')] + ['balanced', 'resilient', 'strict']).unique(),
               description: 'balanced = hard-fail on expired credentials / backup error / no-backup, ' +
                            'but keep going (UNSTABLE) on cooldown + upload-target failures. ' +
                            'resilient = never abort, only mark UNSTABLE. strict = abort on any problem.')
        choice(name: 'JIRA_COOLDOWN_ACTION',
               choices: ([(env.JIRA_COOLDOWN_ACTION ?: 'skip')] + ['skip', 'download-existing']).unique(),
               description: 'On the Jira 48h cooldown: skip Jira (mark unstable), or download the ' +
                            'most recent existing backup instead.')

        // --- Advanced: per-outcome overrides. Leave 'default' to follow the
        //     FAILURE_POLICY preset above; set continue / unstable / abort to
        //     control that one outcome regardless of the preset. ---
        choice(name: 'ON_COOLDOWN',
               choices: ([(env.ON_COOLDOWN ?: 'default')] + ['default', 'continue', 'unstable', 'abort']).unique(),
               description: 'Override for the Jira 48h cooldown outcome')
        choice(name: 'ON_CREDENTIALS',
               choices: ([(env.ON_CREDENTIALS ?: 'default')] + ['default', 'continue', 'unstable', 'abort']).unique(),
               description: 'Override for expired/rejected credentials (Jira cookies or Confluence token)')
        choice(name: 'ON_BACKUP_ERROR',
               choices: ([(env.ON_BACKUP_ERROR ?: 'default')] + ['default', 'continue', 'unstable', 'abort']).unique(),
               description: 'Override for a backup error or timeout')
        choice(name: 'ON_NO_BACKUP',
               choices: ([(env.ON_NO_BACKUP ?: 'default')] + ['default', 'continue', 'unstable', 'abort']).unique(),
               description: 'Override for when NO product produced a backup this run')
        choice(name: 'ON_UPLOAD_FAILURE',
               choices: ([(env.ON_UPLOAD_FAILURE ?: 'default')] + ['default', 'continue', 'unstable', 'abort']).unique(),
               description: 'Override for an upload-target failure')

        // --- What to back up (untick to skip a product entirely) ---
        booleanParam(name: 'BACKUP_JIRA', defaultValue: true,
                     description: 'Run the Jira backup stage')
        booleanParam(name: 'BACKUP_CONFLUENCE', defaultValue: true,
                     description: 'Run the Confluence backup stage')
        booleanParam(name: 'JIRA_DOWNLOAD_EXISTING', defaultValue: false,
                     description: 'Jira: do not trigger a new backup — download the most recent ' +
                                  'existing one (use on cooldown / reruns)')

        // --- Storage targets: tick a box per backend, fill its destination below it.
        //     Defaults come from the global env vars set by jenkins-setup.groovy. ---
        booleanParam(name: 'STORE_GCS', defaultValue: (env.STORAGE_PROVIDER ?: '').contains('gcs'),
                     description: 'Upload to Google Cloud Storage')
        string(name: 'GCS_BUCKET', defaultValue: "${env.GCS_BUCKET ?: ''}",
               description: 'GCS bucket name (used when GCS is ticked)')
        booleanParam(name: 'STORE_S3', defaultValue: (env.STORAGE_PROVIDER ?: '').contains('s3'),
                     description: 'Upload to AWS S3 / S3-compatible (R2 / B2 / MinIO / Spaces)')
        string(name: 'S3_BUCKET', defaultValue: "${env.S3_BUCKET ?: ''}",
               description: 'S3 bucket name (used when S3 is ticked)')
        string(name: 'S3_ENDPOINT_URL', defaultValue: "${env.S3_ENDPOINT_URL ?: ''}",
               description: 'S3-compatible endpoint (R2 / B2 / MinIO / Spaces); blank for AWS')
        booleanParam(name: 'STORE_AZURE', defaultValue: (env.STORAGE_PROVIDER ?: '').contains('azure'),
                     description: 'Upload to Azure Blob Storage')
        string(name: 'AZURE_CONTAINER', defaultValue: "${env.AZURE_CONTAINER ?: ''}",
               description: 'Azure container name (used when Azure is ticked)')
        booleanParam(name: 'STORE_LOCAL', defaultValue: (env.STORAGE_PROVIDER ?: 'local').contains('local'),
                     description: 'Copy to a local / mounted directory on the agent')
        string(name: 'LOCAL_PATH', defaultValue: "${env.LOCAL_PATH ?: ''}",
               description: 'Local directory (used when Local is ticked; blank = build archive dir)')

        // --- Notifications: tick every channel you want a report sent to. ---
        booleanParam(name: 'NOTIFY_GOOGLE_CHAT', defaultValue: (env.NOTIFY_CHANNELS ?: '').contains('google-chat'),
                     description: 'Google Chat')
        booleanParam(name: 'NOTIFY_SLACK', defaultValue: (env.NOTIFY_CHANNELS ?: '').contains('slack'),
                     description: 'Slack')
        booleanParam(name: 'NOTIFY_DISCORD', defaultValue: (env.NOTIFY_CHANNELS ?: '').contains('discord'),
                     description: 'Discord')
        booleanParam(name: 'NOTIFY_TEAMS', defaultValue: (env.NOTIFY_CHANNELS ?: '').contains('teams'),
                     description: 'Microsoft Teams')
        booleanParam(name: 'NOTIFY_EMAIL', defaultValue: (env.NOTIFY_CHANNELS ?: '').contains('email'),
                     description: 'Email (SMTP)')
        booleanParam(name: 'NOTIFY_WEBHOOK', defaultValue: (env.NOTIFY_CHANNELS ?: '').contains('webhook'),
                     description: 'Generic webhook')

        // --- Archive + timing ---
        choice(name: 'ARCHIVE_COMPRESSION',
               choices: ([(env.ARCHIVE_COMPRESSION ?: '5')] + ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']).unique(),
               description: '7-Zip compression: 0 (store) - 9 (ultra)')
        string(name: 'PRODUCT_NAME_TEMPLATE', defaultValue: "${env.PRODUCT_NAME_TEMPLATE ?: '{product}-{date}'}",
               description: 'Tokens: {product}{site}{date}{time}{datetime}{timestamp}')
        string(name: 'ARCHIVE_NAME_TEMPLATE', defaultValue: "${env.ARCHIVE_NAME_TEMPLATE ?: 'atlassian-backup-{date}'}",
               description: 'Archive (.7z) filename template')
        string(name: 'POLL_TIMEOUT', defaultValue: "${env.POLL_TIMEOUT ?: '21600'}",
               description: 'Max seconds to wait for each backup to finish (default 21600 = 6h)')
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
                    //
                    // Assemble aligned STORAGE_PROVIDER / STORAGE_DEST comma lists from
                    // the per-backend checkboxes + their destination fields, so the
                    // Python upload layer keeps receiving the contract it expects.
                    def provs = []
                    def dests = []
                    if (params.STORE_GCS)   { provs << 'gcs';   dests << (params.GCS_BUCKET ?: '') }
                    if (params.STORE_S3)    { provs << 's3';    dests << (params.S3_BUCKET ?: '') }
                    if (params.STORE_AZURE) { provs << 'azure'; dests << (params.AZURE_CONTAINER ?: '') }
                    if (params.STORE_LOCAL) { provs << 'local'; dests << (params.LOCAL_PATH?.trim() ? params.LOCAL_PATH : env.ARCHIVE_DIR) }
                    if (provs.isEmpty())    { provs << 'local'; dests << env.ARCHIVE_DIR }  // safety net: never silently skip upload
                    env.STORAGE_PROVIDER = provs.join(',')
                    env.STORAGE_DEST     = dests.join(',')
                    env.S3_ENDPOINT_URL  = params.S3_ENDPOINT_URL

                    // Notification channels from the per-channel checkboxes.
                    def chans = []
                    if (params.NOTIFY_GOOGLE_CHAT) chans << 'google-chat'
                    if (params.NOTIFY_SLACK)       chans << 'slack'
                    if (params.NOTIFY_DISCORD)     chans << 'discord'
                    if (params.NOTIFY_TEAMS)       chans << 'teams'
                    if (params.NOTIFY_EMAIL)       chans << 'email'
                    if (params.NOTIFY_WEBHOOK)     chans << 'webhook'
                    env.NOTIFY_CHANNELS = chans.join(',')

                    env.PRODUCT_NAME_TEMPLATE = params.PRODUCT_NAME_TEMPLATE
                    env.ARCHIVE_NAME_TEMPLATE = params.ARCHIVE_NAME_TEMPLATE
                    env.ARCHIVE_COMPRESSION   = params.ARCHIVE_COMPRESSION
                    env.POLL_TIMEOUT          = params.POLL_TIMEOUT
                    // Failure policy + cooldown action drive how outcomes are handled.
                    env.FAILURE_POLICY        = params.FAILURE_POLICY
                    env.JIRA_COOLDOWN_ACTION  = params.JIRA_COOLDOWN_ACTION
                    echo "Config: jira=${env.SITE_JIRA} storage=${env.STORAGE_PROVIDER}:" +
                         "${env.STORAGE_DEST} notify=${env.NOTIFY_CHANNELS ?: '(none)'} " +
                         "policy=${env.FAILURE_POLICY} cooldown=${env.JIRA_COOLDOWN_ACTION}"
                    setupVenv()
                }
            }
        }

        // Jira and Confluence are INDEPENDENT. Each module exits with a code that
        // identifies the outcome; runBackup() applies the FAILURE_POLICY preset to
        // decide whether that outcome continues (UNSTABLE) or aborts the build.
        stage('Jira backup') {
            when { expression { params.BACKUP_JIRA } }
            steps {
                withCredentials([
                    string(credentialsId: 'jira-cookies', variable: 'JIRA_COOKIES')
                ]) {
                    script {
                        def extra = params.JIRA_DOWNLOAD_EXISTING ? ' --download-existing' : ''
                        runBackup('Jira', "-m backup.jira --site \"${SITE_JIRA}\" --out \"${OUT_DIR}\"${extra}")
                    }
                }
            }
        }

        stage('Confluence backup') {
            when { expression { params.BACKUP_CONFLUENCE } }
            steps {
                withCredentials([
                    string(credentialsId: 'atlassian-email',     variable: 'ATL_EMAIL'),
                    string(credentialsId: 'atlassian-api-token', variable: 'ATL_TOKEN')
                ]) {
                    script {
                        runBackup('Confluence', "-m backup.confluence --site \"${SITE_CONFLUENCE}\" --out \"${OUT_DIR}\"")
                    }
                }
            }
        }

        stage('Archive') {
            steps {
                script {
                    if (!hasBackups()) {
                        // "No backup produced" outcome — severity per the policy.
                        if (policyFor('nobackup') == 'abort') {
                            error('No Jira or Confluence backup was produced — failing per policy.')
                        }
                        unstable('No Jira or Confluence backup was produced — skipping Archive and Upload.')
                        return
                    }
                    withCredentials([
                        string(credentialsId: 'archive-password', variable: 'ARCHIVE_PASSWORD')
                    ]) {
                        runPy("-m backup.archive --in \"${OUT_DIR}\" --out \"${ARCHIVE_DIR}\"")
                    }
                }
            }
        }

        stage('Upload') {
            when { expression { hasBackups() } }
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
                    // Best-effort across targets; a non-zero exit means at least one
                    // target failed -> 'upload' outcome, severity per the policy.
                    int code = creds ? withCredentials(creds) { runStatus(cmd) } : runStatus(cmd)
                    if (code != 0) {
                        def action = policyFor('upload')
                        echo "[Upload] exit=${code} outcome=upload policy=${params.FAILURE_POLICY ?: 'balanced'} -> ${action}"
                        if (action == 'abort') {
                            error("Upload failed (exit ${code}) — stopping per policy")
                        }
                        unstable("Upload had target failure(s) (exit ${code}) — continuing; build marked UNSTABLE")
                    }
                }
            }
        }

        stage('Notify') {
            steps {
                // Report the REAL outcome: SUCCESS, or UNSTABLE when a product
                // stage failed/was skipped but the rest still completed.
                script { runNotify(currentBuild.currentResult) }
            }
        }
    }

    post {
        // The Notify stage handles the success / unstable paths (and shows as its
        // own box). A hard FAILURE skips it, so notify from here instead.
        failure {
            script { runNotify('failure') }
        }
        always {
            cleanWs()
        }
    }
}
