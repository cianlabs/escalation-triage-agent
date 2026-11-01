# Sources for Real Incident Data and Runbooks

This file lists the public post-mortems, incident write-ups, and troubleshooting runbooks used to build the real dataset in this repository.

All content is summarized in our own words based on openly published technical pages. No private, confidential, or production data is included. Log entries and deploy records without raw logs in the original write-up are reconstructed from the facts stated in the public post-mortem and labeled accordingly.

---

## Incident Post-Mortems (12 Incidents)

### 1. Cloudflare - November 2, 2023 Control Plane Outage
- **Source:** Cloudflare Blog - Post-mortem on November 2, 2023 outage
- **URL:** https://blog.cloudflare.com/post-mortem-on-november-2-2023-outage/
- **Date:** 2023-11-02
- **Symptoms:** Cloudflare dashboard, Control Plane APIs, and log streaming services were unavailable.
- **Root Cause:** Power failure at a primary data center facility coupled with dependent services failing to failover cleanly due to hardcoded configuration references.
- **Fix:** Restored facility power, updated service service-discovery configs, and decoupled control plane dependencies.

### 2. GitHub - October 21, 2018 Database Degradation
- **Source:** GitHub Engineering Blog - October 21 outage post-mortem
- **URL:** https://github.blog/2018-10-21-october-21-post-mortem/
- **Date:** 2018-10-21
- **Symptoms:** Inconsistent data shown across github.com, delayed background jobs, and web request failures.
- **Root Cause:** Maintenance on a 100G optical link caused network partition during database failover, leading to replica database corruption and split-brain states.
- **Fix:** Isolated corrupted database replicas, restored state from clean backups, and rebuilt database replication topologies.

### 3. AWS - December 7, 2021 US-EAST-1 Outage
- **Source:** AWS Summary of the US-EAST-1 Event in December 2021
- **URL:** https://aws.amazon.com/message/11201/
- **Date:** 2021-12-07
- **Symptoms:** AWS Management Console, EC2 APIs, DynamoDB, and dependent internal services failed in US-EAST-1.
- **Root Cause:** Automated scaling of the internal main network caused unexpected capacity pressure on internal router devices, triggering latency and packet loss.
- **Fix:** Disabled automatic scaling behavior on internal network capacity routers and throttled control plane clients.

### 4. Slack - February 22, 2022 Outage
- **Source:** Slack Engineering - Outage Post-Mortem February 22 2022
- **URL:** https://slack.engineering/february-22-2022-outage-post-mortem/
- **Date:** 2022-02-22
- **Symptoms:** Connection failures, messaging delays, and 500 errors across web and desktop applications.
- **Root Cause:** A rolling restart of database clusters triggered connection spikes that overwhelmed AWS Transit Gateway capacity limits.
- **Fix:** Increased Transit Gateway network bandwidth limits and added exponential backoff on client reconnects.

### 5. Datadog - March 8, 2023 Outage
- **Source:** Datadog Post-Mortem: March 8 2023 Service Disruption
- **URL:** https://www.datadoghq.com/blog/post-mortem-march-8-2023-outage/
- **Date:** 2023-03-08
- **Symptoms:** Metrics intake, alerting, and web dashboards unavailable across multiple regions.
- **Root Cause:** An OS package update on container nodes included a broken systemd/containerd interaction, causing systemd unit reloads to kill container runtimes.
- **Fix:** Rolled back kernel/OS package updates across affected node pools and rebuilt control plane nodes.

### 6. CircleCI - January 4, 2023 Security Incident & Outage
- **Source:** CircleCI Security Incident Post-Mortem
- **URL:** https://circleci.com/blog/jan-4-2023-incident-report/
- **Date:** 2023-01-04
- **Symptoms:** Build runner failures, pipeline cancellations, and system access restrictions.
- **Root Cause:** Compromised engineer credentials enabled unauthorized access to production database backups and internal tokens, prompting emergency credential rotation and system lockdown.
- **Fix:** Rotated all OAuth tokens, secrets, and API keys, and purged unauthorized session tokens across clusters.

### 7. Fastly - June 8, 2021 Global Outage
- **Source:** Fastly Blog - Summary of June 8 2021 Outage
- **URL:** https://www.fastly.com/blog/summary-of-june-8-2021-outage/
- **Date:** 2021-06-08
- **Symptoms:** 85% of Fastly CDN network returned 503 errors globally for major web properties.
- **Root Cause:** A customer configuration change triggered a dormant bug in a software deployment rolled out May 12, causing edge proxies to crash on specific request conditions.
- **Fix:** Deactivated the invalid configuration flag and deployed fixed proxy software to all POPs globally.

### 8. Atlassian - April 5, 2022 Cloud Outage
- **Source:** Atlassian Post-Mortem - April 2022 Cloud Outage
- **URL:** https://www.atlassian.com/engineering/post-mortem-april-2022-cloud-outage
- **Date:** 2022-04-05
- **Symptoms:** Jira, Confluence, and Opsgenie sites completely inaccessible for 775 customer tenants.
- **Root Cause:** Faulty automation script executed during legacy app deletion passed incorrect site IDs, deleting live production databases instead of standalone apps.
- **Fix:** Restored customer site databases from isolated backups and verified data integrity for each tenant.

### 9. Google Cloud - November 16, 2021 Networking Incident
- **Source:** Google Cloud Infrastructure Outage Incident 21009
- **URL:** https://status.cloud.google.com/incidents/21009
- **Date:** 2021-11-16
- **Symptoms:** Global 404 errors on Cloud Storage, App Engine, and Cloud Functions assets.
- **Root Cause:** A configuration change pushed to edge network locations contained malformed route policies that caused load balancers to drop traffic.
- **Fix:** Rolled back the edge network configuration change globally.

### 10. Reddit - March 14, 2023 Outage
- **Source:** Reddit Incident Post-Mortem - March 14 2023
- **URL:** https://www.reddit.com/r/reddit/comments/11rc335/outage_post_mortem/
- **Date:** 2023-03-14
- **Symptoms:** Reddit web and mobile apps displayed error screens and failed to load feeds.
- **Root Cause:** Kubernetes cluster upgrade introduced CNI network plugin incompatibility that caused pods to lose network connectivity during rolling node restarts.
- **Fix:** Rolled back Kubernetes node pool upgrades and restored previous CNI plugin configuration.

### 11. OpenAI - November 8, 2023 Outage
- **Source:** OpenAI Status - Periodic Outages Across ChatGPT and API
- **URL:** https://status.openai.com/incidents/2py2v110w9nn
- **Date:** 2023-11-08
- **Symptoms:** ChatGPT and API requests failing with high error rates and HTTP 500/503 responses.
- **Root Cause:** Distributed denial of service (DDoS) attack creating extreme traffic spikes that saturated API gateway capacity limits.
- **Fix:** Enabled elevated DDoS mitigation rules, rate-limited traffic at edge firewalls, and expanded gateway capacity.

### 12. Heroku - September 27, 2021 Build Failures
- **Source:** Heroku Status - Incident Report on Build Pipeline Delays
- **URL:** https://status.heroku.com/incidents/2324
- **Date:** 2021-09-27
- **Symptoms:** Application builds stuck in queued status or timing out during compilation.
- **Root Cause:** Exhaustion of build worker memory and disk space caused by orphaned container build artifacts in worker storage.
- **Fix:** Purged orphan build cache directories and restarted stuck background image-worker processes.

---

## Troubleshooting & Runbook Docs (6 Runbooks)

### 1. AWS EC2 Troubleshooting - High CPU Utilization
- **Source:** AWS EC2 User Guide - Troubleshooting High CPU
- **URL:** https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/troubleshooting-high-cpu.html
- **Date:** 2023-10-15
- **Topic:** Identifying CPU-bound processes, handling noisy neighbors, and restarting or scaling instance worker processes.

### 2. Kubernetes Troubleshooting - Pod OOMKilled
- **Source:** Kubernetes Documentation - Debug Pod Failure
- **URL:** https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/
- **Date:** 2024-01-20
- **Topic:** Investigating memory leaks, OOMKilled pod exit codes, and restarting crashing worker pods.

### 3. Nginx Troubleshooting - 502 Bad Gateway
- **Source:** Nginx Documentation - Pitfalls and Common Errors
- **URL:** https://nginx.org/en/docs/debugging_log.html
- **Date:** 2023-08-10
- **Topic:** Resolving upstream backend failures, socket timeouts, and bad deploy rollbacks.

### 4. PostgreSQL Troubleshooting - Connection Pool Exhaustion
- **Source:** PostgreSQL Documentation - Server Administration and Connection Limits
- **URL:** https://www.postgresql.org/docs/current/runtime-config-connection.html
- **Date:** 2023-11-01
- **Topic:** Managing max connections, handling connection pool exhaustion, and restarting connection pooler services.

### 5. Redis Troubleshooting - Memory Out of Memory Errors
- **Source:** Redis Documentation - Memory Management and Eviction Policies
- **URL:** https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/memory/
- **Date:** 2023-09-12
- **Topic:** Handling Redis maxmemory reached errors, eviction policies, and cache node restarts.

### 6. Datadog / PagerDuty - Sev-1 Incident Escalation Runbook
- **Source:** PagerDuty Incident Response Guide
- **URL:** https://response.pagerduty.com/before/different_roles/
- **Date:** 2023-05-18
- **Topic:** Criteria for declaring customer-facing outages, escalating to on-call engineers, and paging incident commanders.
