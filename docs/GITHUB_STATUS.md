# One real source, two practice sources

```sh
python agent.py --github-status
```

This mode makes one read-only GET request to GitHub's public status API. Recent errors and recent changes still come from simulated readers. Output labels each source and prints both practice observations as excluded. The program does not use those invented clues to investigate real GitHub status.

The live observation keeps the endpoint URL, fetch time, status-page update time and reported aggregate indicator. It is evidence of what GitHub's status page reported, not proof of the health or cause of a problem in your own service. A status-page update time is not the incident start time or a measure of how recently every component was checked.

## What the result means

GitHub documents four rollup indicators: none, minor, major and critical. The connector displays the reported value, plus the provider's description. The value none means the provider reports no aggregate impact; it is not a promise that every request or component is healthy. The endpoint does not identify a root cause. See [GitHub's status API documentation](https://www.githubstatus.com/api).

Only a validated live status observation enters investigation. The provider's free-text description is displayed but excluded from causal matching. A description mentioning a crash, an expired token or a rollback therefore cannot turn aggregate status into a diagnosis. The existing ranker and its evaluation rules are unchanged. The new mode remains uncertain and leaves confirmed_root_cause empty.

If the request fails, times out, redirects, returns a non-200 status, contains invalid JSON or has an unexpected page, indicator or timestamp, GitHub status is unknown. No healthy observation is invented or cached from an earlier request. The two successful practice checks do not turn an unknown GitHub result into success: this command exits 1 unless a valid public report was obtained. It exits 0 for any valid indicator, including major or critical, because that exit code describes collection success rather than health.

## Request boundary

The fixed endpoint is https://www.githubstatus.com/api/v2/status.json. It requires no API key or account sign-in. A fresh httpx.AsyncClient sends GET with no request body, no authorization and no account cookies. The symptom, synthetic clues, local files and model keys are not sent. Redirects are not followed. The client ignores environment proxy settings and uses normal certificate verification. There are no automatic retries.

The request has a four-second HTTP timeout and the reader has a five-second overall collection deadline. The two simulated readers start concurrently with it. Timeout and cancellation handling are inherited from the async collector. The HTTP client is closed when collection finishes or is cancelled. This mode never enters the live-model workflow, saved-memory handling or action approval path.

## Provenance in the collector

EvidenceCheck now declares a data_kind: synthetic, public_status or unspecified. The collector assigns that value rather than trusting a claim in a returned row. Every observation retains its source namespace. Selected timestamp and status metadata are preserved through collection.

The mixed mode accepts only public_status evidence for investigation. Excluded practice ids remain visible in the result. Existing fully simulated collection commands still operate on their practice observations; their behavior is unchanged.

## Verification

A manual live request succeeded on November 1, 2026, Pacific time. That verifies the integration at one moment, not ongoing availability. Automated tests use httpx.MockTransport and never request the public endpoint. They cover each documented indicator, network and HTTP failures, redirects, malformed payloads, page identity, timestamps, excluded synthetic clues and free text, source provenance, concurrent start, read-only CLI behavior and exit codes.

Run:

```sh
python -m pytest -q
python evaluation.py --check
python investigation_eval.py --check
```

The original public and synthetic ranking reports reproduce unchanged. This integration adds live evidence collection; it does not establish a diagnosis improvement or a production-ready incident response service.

## Learning exercise

Read the three source labels in the output. Identify which source contacted a real service and which two did not. Find the two timestamps and explain why they mean different things. Finally, explain why a failed status request must mean unknown, and why a valid major indicator still cannot explain what caused your own problem.
