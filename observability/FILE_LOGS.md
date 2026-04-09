# File-Based Logs to Loki

The default local path for backend workflow logs should be container standard output and standard error.

That path is simpler because Docker already captures it, and Grafana Alloy can ship it to Loki without application code pushing directly to Loki.

## When File Logs Are Still Useful

File-based logs are still useful when:
- a smoke test writes logs from `docker compose exec`, which does not become part of the long-running container log stream
- a third-party process can only write to disk
- you want to preserve a separate local audit file in addition to container logs

## What File-Based Shipping Requires

If a process writes logs to a file and you want those logs in Loki, you need more than just the application container.

You need:
- the log file path to exist inside the producing container or on the host
- that path to be mounted into the Alloy container
- an Alloy `local.file_match` rule that points at the mounted path
- an Alloy `loki.source.file` component that forwards those files to Loki
- persistent Alloy storage if you want file offsets to survive collector restarts

This repository already does that for the smoke tests by mounting `observability/test/logs` into Alloy and matching `/var/observability/test/logs/*.log`.

## Minimal Alloy Pattern

```alloy
local.file_match "example_logs" {
  path_targets = [
    {
      __path__ = "/var/my-app/logs/*.log"
      job      = "my-app-file-logs"
      service  = "my-app"
      source   = "file"
    },
  ]
}

loki.source.file "example_logs" {
  targets    = local.file_match.example_logs.targets
  forward_to = [loki.write.local.receiver]
}
```

## Recommendation For This Repo

For backend workflow telemetry, keep using standard output and standard error.

Choose file-based ingestion only when one of these is true:
- the producer is not a long-running container process
- the output comes from `docker compose exec`
- a tool is fixed to disk output and cannot be changed

If backend logs ever move to files, mount that log directory into Alloy and add another `local.file_match` plus `loki.source.file` pair.