// ─────────────────────────────────────────────────────────────────────────────
// Jenkinsfile — Multi-Server Health Check & Virus Scanner
// ─────────────────────────────────────────────────────────────────────────────
//
// SETUP CHECKLIST (do once in Jenkins):
//
//  1. Install plugins:
//       - "HTML Publisher"     → renders HTML reports in Jenkins UI
//       - "Pipeline Utility Steps" → for readJSON()
//
//  2. Install sshpass on the Jenkins agent:
//       sudo apt-get install -y sshpass rsync
//
//  3. Add one credential per server:
//       Jenkins → Manage Jenkins → Credentials → Global → Add Credential
//       Kind: "Username with password"
//       ID:    must match the "cred_id" field in servers.json
//
//  4. Edit servers.json to list your servers.
//
//  5. (Optional) Set ALERT_EMAIL below.
// ─────────────────────────────────────────────────────────────────────────────

pipeline {

    agent any

    // ── Configurable parameters ───────────────────────────────────────────────
    parameters {
        booleanParam(
            name: 'SKIP_VIRUS_SCAN',
            defaultValue: false,
            description: 'Skip ClamAV scan (faster health-check-only run)'
        )
        string(
            name: 'MAX_FILESIZE_MB',
            defaultValue: '100',
            description: 'Max file size (MB) for ClamAV to scan'
        )
    }

    // ── Environment ───────────────────────────────────────────────────────────
    environment {
        APP_SRC      = "${WORKSPACE}"
        REPORT_DEST  = "${WORKSPACE}/reports"
        SERVERS_FILE = "${WORKSPACE}/servers.json"
    }

    options {
        timestamps()
        timeout(time: 3, unit: 'HOURS')
        buildDiscarder(logRotator(numToKeepStr: '30'))
    }

    stages {

        // ── Stage 0: Validate environment ─────────────────────────────────────
        stage('Validate') {
            steps {
                script {
                    echo "═══ Validating Jenkins agent environment ═══"

                    // Check sshpass
                    sh '''
                        if ! command -v sshpass >/dev/null 2>&1; then
                            echo "sshpass not found on Jenkins agent!"
                            echo "Run: sudo apt-get install -y sshpass"
                            exit 1
                        fi
                        echo "sshpass OK: $(sshpass -V 2>&1 | head -1)"
                    '''

                    // Check servers.json
                    if (!fileExists(env.SERVERS_FILE)) {
                        error "servers.json not found at ${env.SERVERS_FILE}"
                    }

                    def servers = readJSON file: env.SERVERS_FILE
                    echo "✅ Found ${servers.size()} server(s) in servers.json:"
                    servers.each { s ->
                        echo "   → [${s.label}] ${s.user}@${s.host}  (cred: ${s.cred_id})"
                    }

                    // Prepare reports dir
                    sh "mkdir -p ${env.REPORT_DEST}"

                    // Make scripts executable
                    sh "chmod +x ${WORKSPACE}/jenkins/deploy_and_run.sh"
                }
            }
        }

        // ── Stage 1: Run health check on ALL servers (in parallel) ────────────
        stage('Health Check — All Servers') {
            steps {
                script {
                    def servers = readJSON file: env.SERVERS_FILE

                    // Build a parallel branch for each server
                    def parallelBranches = [:]
                    def virusFoundServers = []

                    servers.each { server ->
                        def s = server  // capture for closure

                        parallelBranches["${s.label} (${s.host})"] = {
                            stage("${s.label}") {
                                withCredentials([
                                    usernamePassword(
                                        credentialsId: s.cred_id,
                                        usernameVariable: 'CRED_USER',
                                        passwordVariable: 'CRED_PASS'
                                    )
                                ]) {
                                    script {
                                        def scanDirs = s.scan_dirs ?: '/home /tmp /etc'
                                        def skipScan = params.SKIP_VIRUS_SCAN ? '--skip-virus-scan' : ''

                                        def exitCode = sh(
                                            returnStatus: true,
                                            script: """
                                                export REMOTE_HOST="${s.host}"
                                                export REMOTE_USER="${CRED_USER}"
                                                export REMOTE_PASS="${CRED_PASS}"
                                                export REMOTE_LABEL="${s.label}"
                                                export SCAN_DIRS="${scanDirs}"
                                                export APP_SRC="${env.APP_SRC}"
                                                export REPORT_DEST="${env.REPORT_DEST}"
                                                export ALERT_EMAIL="${params.ALERT_EMAIL}"
                                                export MAX_FILESIZE="${params.MAX_FILESIZE_MB}"
                                                bash ${WORKSPACE}/jenkins/deploy_and_run.sh
                                            """
                                        )

                                        if (exitCode == 2) {
                                            // Virus found — mark build unstable but continue
                                            unstable("VIRUS DETECTED on ${s.label}!")
                                            virusFoundServers << s.label
                                        } else if (exitCode != 0) {
                                            // Connection or script error — warn but don't kill the build
                                            unstable("Health check FAILED on ${s.label} (exit ${exitCode}) — check SSH/credentials")
                                            echo "ERROR on ${s.label}: exit code ${exitCode}. Other servers continue."
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // Run all servers in parallel
                    parallel parallelBranches

                    // Store virus results for post stage
                    env.VIRUS_FOUND_SERVERS = virusFoundServers.join(', ')
                }
            }
        }

        // ── Stage 2: Publish reports ───────────────────────────────────────────
        stage('Publish Reports') {
            steps {
                script {
                    echo "═══ Publishing HTML reports ═══"

                    // Build a combined index page listing all server reports
                    def servers = readJSON file: env.SERVERS_FILE
                    def indexHtml = buildIndexPage(servers, env.VIRUS_FOUND_SERVERS)
                    writeFile file: "${env.REPORT_DEST}/index.html", text: indexHtml
                }

                // Archive all reports as Jenkins build artifacts
                archiveArtifacts(
                    artifacts: 'reports/**/*.html, reports/**/*.json, reports/**/*.txt',
                    allowEmptyArchive: true,
                    fingerprint: true
                )

                // Publish HTML reports with the HTML Publisher plugin
                publishHTML(target: [
                    allowMissing         : true,
                    alwaysLinkToLastBuild: true,
                    keepAll              : true,
                    reportDir            : 'reports',
                    reportFiles          : 'index.html',
                    reportName           : '🔍 Health Check Reports',
                    reportTitles         : 'Server Health Check Dashboard'
                ])

                echo "✅ Reports published. View in sidebar: '🔍 Health Check Reports'"
            }
        }
    }

    // ── Post-build actions ─────────────────────────────────────────────────────
    post {
        always {
            script {
                echo "═══ Build Summary ═══"
                sh """
                    echo "Reports directory:"
                    ls -lh ${env.REPORT_DEST}/ 2>/dev/null || echo "(empty)"
                    echo ""
                    echo "Server statuses:"
                    find ${env.REPORT_DEST}/ -name '*_status.txt' 2>/dev/null | while IFS= read -r f; do
                        cat "\$f"
                        echo "---"
                    done || true
                """
            }
        }

        unstable {
            script {
                if (env.VIRUS_FOUND_SERVERS) {
                    echo "VIRUS ALERT: Infected servers: ${env.VIRUS_FOUND_SERVERS}"
                    echo "Check the Health Check Reports in Jenkins sidebar for details."
                } else {
                    echo "One or more servers had connection/script errors. Check console output above."
                }
            }
        }

        failure {
            echo "Pipeline failed. Check console output for details."
        }

        success {
            echo "All servers healthy. No viruses detected."
        }
    }
}


// ─────────────────────────────────────────────────────────────────────────────
// Helper: Build a combined HTML index page for all server reports
// ─────────────────────────────────────────────────────────────────────────────
def buildIndexPage(servers, virusFoundServers) {
    def virusList = (virusFoundServers ?: '').split(',').collect { it.trim() }.findAll { it }
    def overallOk = virusList.isEmpty()
    def ts = new Date().format("yyyy-MM-dd HH:mm:ss")

    def rows = servers.collect { s ->
        def infected = virusList.contains(s.label)
        def statusBadge = infected
            ? '<span class="badge danger">⚠️ VIRUS FOUND</span>'
            : '<span class="badge ok">✅ CLEAN</span>'
        def reportLink = "<a href='${s.label}_latest.html' target='_blank'>View Report</a>"
        def jsonLink   = "<a href='${s.label}_latest.json' target='_blank'>JSON</a>"
        """<tr class="${infected ? 'row-danger' : ''}">
             <td><strong>${s.label}</strong></td>
             <td>${s.host}</td>
             <td>${s.description ?: ''}</td>
             <td>${statusBadge}</td>
             <td>${reportLink} &nbsp; ${jsonLink}</td>
           </tr>"""
    }.join('\n')

    def overallBanner = overallOk
        ? '<div class="banner ok">✅ ALL SERVERS HEALTHY</div>'
        : "<div class=\"banner danger\">🔴 VIRUS DETECTED ON: ${virusList.join(', ')}</div>"

    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Health Check Dashboard — ${ts}</title>
  <style>
    :root { --bg:#0f1117; --surface:#1a1d27; --accent:#6366f1; --text:#e2e8f0;
            --muted:#94a3b8; --ok:#4ade80; --danger:#f87171; --border:rgba(255,255,255,.07); }
    * { box-sizing:border-box; margin:0; padding:0; }
    body { background:var(--bg); color:var(--text); font-family:'Segoe UI',system-ui,sans-serif; padding:0; }
    header { background:linear-gradient(135deg,#1e1b4b,#312e81,#1e1b4b); padding:36px 48px; }
    header h1 { font-size:2rem; font-weight:700; background:linear-gradient(90deg,#a5b4fc,#e879f9);
                -webkit-background-clip:text; -webkit-text-fill-color:transparent; }
    header p  { color:var(--muted); margin-top:6px; }
    .container { max-width:1200px; margin:0 auto; padding:32px 48px; }
    .banner { border-radius:12px; padding:20px 28px; font-size:1.3rem; font-weight:700; margin-bottom:28px; }
    .banner.ok     { background:rgba(74,222,128,.1); color:var(--ok); border:1px solid rgba(74,222,128,.3); }
    .banner.danger { background:rgba(248,113,113,.1); color:var(--danger); border:1px solid rgba(248,113,113,.3); }
    table { width:100%; border-collapse:collapse; background:var(--surface);
            border-radius:12px; overflow:hidden; border:1px solid var(--border); }
    th { background:#22263a; color:var(--muted); text-align:left; padding:12px 18px;
         font-size:.8rem; text-transform:uppercase; letter-spacing:.05em; }
    td { padding:14px 18px; border-bottom:1px solid var(--border); }
    tr:last-child td { border-bottom:none; }
    tr.row-danger td { background:rgba(248,113,113,.05); }
    a  { color:#818cf8; text-decoration:none; }
    a:hover { text-decoration:underline; }
    .badge { display:inline-block; padding:4px 12px; border-radius:20px; font-size:.78rem; font-weight:700; }
    .badge.ok     { background:rgba(74,222,128,.15); color:var(--ok); }
    .badge.danger { background:rgba(248,113,113,.15); color:var(--danger); }
    footer { text-align:center; padding:28px; color:var(--muted); font-size:.8rem; }
  </style>
</head>
<body>
<header>
  <h1>🔍 Server Health Check Dashboard</h1>
  <p>Jenkins Pipeline Run &nbsp;|&nbsp; Generated: <strong>${ts}</strong> &nbsp;|&nbsp;
     Build: <strong>${env.JOB_NAME} #${env.BUILD_NUMBER}</strong></p>
</header>
<div class="container">
  ${overallBanner}
  <table>
    <thead>
      <tr><th>Server</th><th>Host</th><th>Description</th><th>Status</th><th>Reports</th></tr>
    </thead>
    <tbody>${rows}</tbody>
  </table>
</div>
<footer>Generated by Jenkins Health Check Pipeline</footer>
</body>
</html>"""
}
