# Performance Dashboard

Last Updated: ${TIMESTAMP}

## Current Performance

| Metric | Value | Status |
|--------|-------|--------|
| Throughput | $(echo $METRICS | jq -r .throughput) req/s | $([ $(echo $METRICS | jq -r .throughput) -gt 500 ] && echo "✅" || echo "⚠️") |
| P99 Latency | $(echo $METRICS | jq -r .p99_latency) ms | $([ $(echo $METRICS | jq -r .p99_latency) -lt 200 ] && echo "✅" || echo "⚠️") |
| Degradation | $(echo $METRICS | jq -r .degradation)% | $([ $(echo $METRICS | jq -r .degradation) -lt 10 ] && echo "✅" || echo "⚠️") |

## Trend

See [metrics history](.metrics/history.jsonl) for detailed trend analysis.

## Automated Monitoring

- Performance checks run every 6 hours
- Full investigation triggered on threshold violations
- PR checks prevent performance regressions

