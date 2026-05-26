// Atlassian weekly backup pipeline
// Runs every Thursday ~02:00
// Stages are independent: Jira cookie expiry does NOT break Confluence stage
//
// Storage and notifications are pluggable — set STORAGE_PROVIDER and
// NOTIFY_CHANNELS below; the pipeline installs the matching SDK and binds the
// matching credentials automatically.

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
        // ── Atlassian site (edit per deployment — not secret) ──
        SITE_JIRA        = 'https://<YOUR_SITE>.atlassian.net'
        SITE_CONFLUENCE  = 'https://<YOUR_SITE>.atlassian.net/wiki'

        // ── Storage: gcs | s3 | azure | local ──
        STORAGE_PROVIDER = 'gcs'
        STORAGE_DEST     = '<YOUR_BUCKET>'   // bucket / container / directory
        S3_ENDPOINT_URL  = ''                // optional R2/B2/MinIO/Spaces (s3 only)

        // ── Notifications: comma list of ──
        // google-chat,slack,discord,teams,email,webhook
        NOTIFY_CHANNELS  = 'google-chat'

        // ── Filename templates (tokens: {product}{site}{date}{time}{datetime}{timestamp}) ──
        PRODUCT_NAME_TEMPLATE = '{product}-{date}'
        ARCHIVE_NAME_TEMPLATE = 'atlassian-backup-{date}'

        // ── Archive compression: 0=store … 9=ultra (encryption uses archive-password cred) ──
        ARCHIVE_COMPRESSION = '5'

        OUT_DIR          = "${WORKSPACE}/out"
        ARCHIVE_DIR      = "${WORKSPACE}/archive"
    }

    stages {

        stage('Setup') {
            steps {
                cleanWs()
                checkout scm
                sh '''
                    set -e
                    python3 -m venv venv
                    . venv/bin/activate
                    pip install --quiet --upgrade pip
                    pip install --quiet -r requirements.txt
                    # Install only the selected provider's SDK (local needs none)
                    if [ "$STORAGE_PROVIDER" != "local" ]; then
                        pip install --quiet -r "requirements-${STORAGE_PROVIDER}.txt"
                    fi
                    mkdir -p "$OUT_DIR" "$ARCHIVE_DIR"
                '''
            }
        }

        stage('Jira backup') {
            steps {
                withCredentials([
                    string(credentialsId: 'jira-cookies', variable: 'JIRA_COOKIES')
                ]) {
                    sh '''
                        set -e
                        . venv/bin/activate
                        python -m backup.jira \
                            --site "$SITE_JIRA" \
                            --out "$OUT_DIR"
                    '''
                }
            }
        }

        stage('Confluence backup') {
            steps {
                withCredentials([
                    string(credentialsId: 'atlassian-email',     variable: 'ATL_EMAIL'),
                    string(credentialsId: 'atlassian-api-token', variable: 'ATL_TOKEN')
                ]) {
                    sh '''
                        set -e
                        . venv/bin/activate
                        python -m backup.confluence \
                            --site "$SITE_CONFLUENCE" \
                            --out "$OUT_DIR"
                    '''
                }
            }
        }

        stage('Archive (7z AES-256)') {
            steps {
                withCredentials([
                    string(credentialsId: 'archive-password', variable: 'ARCHIVE_PASSWORD')
                ]) {
                    sh '''
                        set -e
                        . venv/bin/activate
                        python -m backup.archive \
                            --in "$OUT_DIR" \
                            --out "$ARCHIVE_DIR"
                    '''
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
                            sh '''
                                set -e
                                . venv/bin/activate
                                python -m backup.upload --provider gcs \
                                    --dest "$STORAGE_DEST" --in "$ARCHIVE_DIR"
                            '''
                        }
                    } else if (env.STORAGE_PROVIDER == 's3') {
                        withCredentials([
                            string(credentialsId: 'aws-access-key-id',     variable: 'AWS_ACCESS_KEY_ID'),
                            string(credentialsId: 'aws-secret-access-key', variable: 'AWS_SECRET_ACCESS_KEY')
                        ]) {
                            sh '''
                                set -e
                                . venv/bin/activate
                                python -m backup.upload --provider s3 \
                                    --dest "$STORAGE_DEST" --in "$ARCHIVE_DIR" \
                                    ${S3_ENDPOINT_URL:+--endpoint-url "$S3_ENDPOINT_URL"}
                            '''
                        }
                    } else if (env.STORAGE_PROVIDER == 'azure') {
                        withCredentials([string(credentialsId: 'azure-storage-connection-string',
                                                variable: 'AZURE_STORAGE_CONNECTION_STRING')]) {
                            sh '''
                                set -e
                                . venv/bin/activate
                                python -m backup.upload --provider azure \
                                    --dest "$STORAGE_DEST" --in "$ARCHIVE_DIR"
                            '''
                        }
                    } else {  // local
                        sh '''
                            set -e
                            . venv/bin/activate
                            python -m backup.upload --provider local \
                                --dest "$STORAGE_DEST" --in "$ARCHIVE_DIR"
                        '''
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

                withCredentials(creds) {
                    sh """
                        . venv/bin/activate || true
                        python -m backup.notify \
                            --channels "${env.NOTIFY_CHANNELS}" \
                            --status ${status} \
                            --archive-dir "${env.ARCHIVE_DIR}" \
                            --build-url "${env.BUILD_URL}" || true
                    """
                }
            }
            cleanWs()
        }
    }
}
