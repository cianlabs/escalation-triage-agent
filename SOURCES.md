# Sources for Real Incident Data and Runbooks

This file lists the public post-mortems, incident write-ups, and troubleshooting runbooks used to build the real dataset in this repository.

All content is summarized in our own words based on openly published technical pages. No private, confidential, or production data is included. Log entries and deploy records without raw logs in the original write-up are reconstructed from the facts stated in the public post-mortem and labeled accordingly.

Every URL listed below has been fetched and verified to return HTTP 200.

---

## Incident Post-Mortems (12 Incidents)

### 1. Cloudflare - November 2, 2023 Control Plane Outage
- **Source:** Cloudflare Blog - Post mortem on the Cloudflare Control Plane and Analytics Outage
- **URL:** https://blog.cloudflare.com/post-mortem-on-cloudflare-control-plane-and-analytics-outage/
- **Date:** 2023-11-02
- **Symptoms:** Beginning at 11:43 UTC, Cloudflare's control plane and analytics services experienced an outage. Users saw errors on the dashboard and APIs, and raw log services were unavailable.
- **Root Cause:** Data center power failure at Flexential PDX-04 followed by faulty circuit breakers and dependent services failing to fail over cleanly.
- **Fix:** Restored facility power, updated service discovery configs, and decoupled control plane dependencies across disaster recovery sites.

### 2. GitHub - October 21, 2018 Database Degradation
- **Source:** GitHub Engineering Blog - October 21 post-incident analysis
- **URL:** https://github.blog/news-insights/company-news/oct21-post-incident-analysis/
- **Date:** 2018-10-21
- **Symptoms:** Multiple services on GitHub.com were affected by degraded service for 24 hours. The site displayed information that was out of date and inconsistent.
- **Root Cause:** Routine optical network maintenance caused a 43-second network partition, triggering database replica failovers into split-brain states.
- **Fix:** Isolated corrupted database replicas, restored state from clean backups, and rebuilt database replication topologies.

### 3. AWS - December 7, 2021 US-EAST-1 Outage
- **Source:** AWS Summary of the US-EAST-1 Event in December 2021
- **URL:** https://aws.amazon.com/message/11201/
- **Date:** 2021-12-07
- **Symptoms:** AWS Management Console, EC2 APIs, DynamoDB, and dependent internal services failed in US-EAST-1 with latent and packet loss issues.
- **Root Cause:** Automated scaling of the internal main network caused unexpected capacity pressure on internal router devices, triggering latency and packet loss.
- **Fix:** Disabled automatic scaling behavior on internal network capacity routers and throttled control plane clients.

### 4. Slack - February 22, 2022 Outage
- **Source:** Slack Engineering - Slack’s Incident on 2-22-22
- **URL:** https://slack.engineering/slacks-incident-on-2-22-22/
- **Date:** 2022-02-22
- **Symptoms:** Many users were unable to connect to Slack or boot their clients, receiving error pages and connection timeouts.
- **Root Cause:** A rolling Consul agent upgrade caused Memcached cache node replacements, exposing an expensive Vitess scatter query that overwhelmed database clusters.
- **Fix:** Throttled client boot requests, updated the scatter query to read from replicas, and allowed caches to refill.

### 5. Datadog - March 8, 2023 Outage
- **Source:** Datadog Engineering - 2023-03-08 Incident: Infrastructure connectivity issue affecting multiple regions
- **URL:** https://www.datadoghq.com/blog/2023-03-08-multiregion-infrastructure-connectivity-issue/
- **Date:** 2023-03-08
- **Symptoms:** Users could not access the platform or various Datadog services via browser or APIs; monitors were unavailable and data ingestion was impacted across US1, EU1, US3, US4, and US5 regions.
- **Root Cause:** An automatic systemd security update triggered a systemd-networkd restart that deleted Cilium CNI container routing rules across VM node pools.
- **Fix:** Disabled the update trigger, rebooted/restarted affected VM instances, and restored container CNI routes.

### 6. CircleCI - January 4, 2023 Security Incident & Outage
- **Source:** CircleCI - Jan 4 2023 Incident Report
- **URL:** https://circleci.com/blog/jan-4-2023-incident-report/
- **Date:** 2023-01-04
- **Symptoms:** Build runner cancellations, system access restrictions, and security rotation lockdown across pipeline runners.
- **Root Cause:** Compromised engineer credentials enabled unauthorized access to production database backups and internal tokens, prompting emergency credential rotation and system lockdown.
- **Fix:** Rotated all OAuth tokens, secrets, and API keys, and purged unauthorized session tokens across clusters.

### 7. Fastly - June 8, 2021 Global Outage
- **Source:** Fastly Blog - Summary of June 8 outage
- **URL:** https://www.fastly.com/blog/summary-of-june-8-outage
- **Date:** 2021-06-08
- **Symptoms:** 85% of Fastly CDN network returned errors globally for major web properties starting at 09:47 UTC.
- **Root Cause:** A customer configuration change triggered a dormant bug in a software deployment rolled out May 12, causing edge proxies to crash on specific request conditions.
- **Fix:** Deactivated the invalid configuration flag and deployed fixed proxy software to all POPs globally.

### 8. Atlassian - April 5, 2022 Cloud Outage
- **Source:** Inside Atlassian - Post-Incident Review on the Atlassian April 2022 outage
- **URL:** https://www.atlassian.com/blog/how-we-build/post-incident-review-april-2022-outage
- **Date:** 2022-04-05
- **Symptoms:** Starting at 7:38 UTC, 775 customer tenants lost access to Jira, Confluence, and Opsgenie cloud sites with HTTP 404/500 errors.
- **Root Cause:** A standalone app deletion script executed with incorrect site IDs deleted live customer site databases instead of legacy app installations.
- **Fix:** Restored customer site databases from isolated backups and verified data integrity for each tenant.

### 9. Google Cloud - November 16, 2021 Networking Incident
- **Source:** Google Cloud Service Health - Incident details 6PM5mNd43NbMqjCZ5REh
- **URL:** https://status.cloud.google.com/incidents/6PM5mNd43NbMqjCZ5REh
- **Date:** 2021-11-16
- **Symptoms:** Affected customers received Google 404 errors in response to HTTP/S requests served by Google External Proxy Load Balancing (GCLB).
- **Root Cause:** A configuration pipeline race condition pushed corrupted configuration files to GCLB proxy instances.
- **Fix:** Restored the last known good configuration and froze GCLB configuration updates until pipeline input validation patches were verified.

### 10. Reddit - March 14, 2023 Outage
- **Source:** Reddit Engineering - You Broke Reddit: The Pi-Day Outage
- **URL:** https://postmortem.io/incidents/reddit--2023-03-21--pi-day-outage/
- **Date:** 2023-03-14
- **Symptoms:** The site came to a screeching halt for 314 minutes; users saw Snoo error pages or homepage feeds with no posts.
- **Root Cause:** Upgrading Kubernetes from 1.23 to 1.24 broke route reflector node metadata and cluster DNS resolution.
- **Fix:** Restored cluster state from clean backups and fixed CNI route reflector node configurations.

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

### 5. Redis Troubleshooting - Memory Optimization
- **Source:** Redis Documentation - Memory optimization
- **URL:** https://redis.io/docs/latest/operate/oss_and_stack/management/optimization/memory-optimization/
- **Date:** 2023-09-12
- **Topic:** Handling Redis maxmemory reached errors, eviction policies, and cache node restarts.

### 6. Datadog / PagerDuty - Sev-1 Incident Escalation Runbook
- **Source:** PagerDuty Incident Response Guide
- **URL:** https://response.pagerduty.com/before/different_roles/
- **Date:** 2023-05-18
- **Topic:** Criteria for declaring customer-facing outages, escalating to on-call engineers, and paging incident commanders.
