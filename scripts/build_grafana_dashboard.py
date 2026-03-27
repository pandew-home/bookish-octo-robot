#!/usr/bin/env python3
"""Builds the K8sGPT Grafana dashboard payload and writes it to /tmp/grafana-payload.json."""
import json

dashboard = {
    "title": "K8sGPT Findings & Fixes",
    "uid": "k8sgpt-findings-v2",
    "tags": ["k8sgpt"],
    "schemaVersion": 38,
    "version": 1,
    "refresh": "5m",
    "time": {"from": "now-7d", "to": "now"},
    "panels": [
        {
            "id": 1, "type": "stat", "title": "Total Active Findings",
            "gridPos": {"h": 4, "w": 4, "x": 0, "y": 0},
            "datasource": {"type": "loki", "uid": "loki"},
            "fieldConfig": {"defaults": {"color": {"mode": "thresholds"}, "thresholds": {"steps": [{"color": "green", "value": 0}, {"color": "yellow", "value": 5}, {"color": "red", "value": 10}]}}},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background"},
            "targets": [{"datasource": {"type": "loki", "uid": "loki"}, "expr": 'count(count_over_time({source="k8sgpt-result"}[7d]))', "instant": True, "refId": "A"}]
        },
        {
            "id": 2, "type": "piechart", "title": "Findings by Kind",
            "gridPos": {"h": 8, "w": 8, "x": 4, "y": 0},
            "datasource": {"type": "loki", "uid": "loki"},
            "options": {"pieType": "pie", "displayLabels": ["name", "value"]},
            "targets": [{"datasource": {"type": "loki", "uid": "loki"}, "expr": 'count by (kind) (count_over_time({source="k8sgpt-result"}[7d]))', "instant": True, "legendFormat": "{{kind}}", "refId": "A"}]
        },
        {
            "id": 4, "type": "logs", "title": "K8sGPT Findings \u2014 Error & [FIX] Highlighted",
            "gridPos": {"h": 20, "w": 24, "x": 0, "y": 8},
            "datasource": {"type": "loki", "uid": "loki"},
            "options": {"dedupStrategy": "none", "enableLogDetails": True, "prettifyLogMessage": True, "showLabels": False, "showTime": True, "sortOrder": "Descending", "wrapLogMessage": True},
            "targets": [{"datasource": {"type": "loki", "uid": "loki"}, "expr": '{source="k8sgpt-result"} | json | line_format "\ud83d\udd34 {{.kind}} \u2014 {{.resource_ns}}/{{.resource}}\\n\u274c ERROR: {{.error}}\\n\u2705 FIX: {{.fix}}\\n\ud83d\udcdd DETAILS: {{.details}}\\n\ud83d\udd50 Found: {{.found_at}}"', "refId": "A"}]
        },
        {
            "id": 5, "type": "table", "title": "Findings Table (sortable)",
            "gridPos": {"h": 18, "w": 24, "x": 0, "y": 28},
            "datasource": {"type": "loki", "uid": "loki"},
            "options": {"frameIndex": 0, "showHeader": True, "sortBy": [{"displayName": "found_at", "desc": True}]},
            "fieldConfig": {"overrides": [
                {"matcher": {"id": "byName", "options": "fix"}, "properties": [{"id": "custom.width", "value": 500}, {"id": "custom.displayMode", "value": "color-background"}, {"id": "color", "value": {"mode": "fixed", "fixedColor": "dark-green"}}]},
                {"matcher": {"id": "byName", "options": "error"}, "properties": [{"id": "custom.width", "value": 400}, {"id": "custom.displayMode", "value": "color-background"}, {"id": "color", "value": {"mode": "fixed", "fixedColor": "dark-red"}}]},
                {"matcher": {"id": "byName", "options": "kind"}, "properties": [{"id": "custom.width", "value": 90}]},
                {"matcher": {"id": "byName", "options": "resource"}, "properties": [{"id": "custom.width", "value": 200}]},
                {"matcher": {"id": "byName", "options": "resource_ns"}, "properties": [{"id": "custom.width", "value": 120}]},
                {"matcher": {"id": "byName", "options": "resource_path"}, "properties": [{"id": "custom.width", "value": 280}]},
                {"matcher": {"id": "byName", "options": "details"}, "properties": [{"id": "custom.width", "value": 400}]},
                {"matcher": {"id": "byName", "options": "found_at"}, "properties": [{"id": "custom.width", "value": 160}]},
                {"matcher": {"id": "byName", "options": "Time"}, "properties": [{"id": "custom.hidden", "value": True}]},
                {"matcher": {"id": "byName", "options": "source"}, "properties": [{"id": "custom.hidden", "value": True}]},
                {"matcher": {"id": "byName", "options": "namespace"}, "properties": [{"id": "custom.hidden", "value": True}]},
            ]},
            "targets": [{"datasource": {"type": "loki", "uid": "loki"}, "expr": '{source="k8sgpt-result"} | json found_at="found_at", kind="kind", resource="resource", resource_ns="resource_ns", resource_path="resource_path", error="error", fix="fix", details="details", backend="backend"', "instant": False, "refId": "A"}]
        }
    ]
}

payload = json.dumps({"dashboard": dashboard, "overwrite": True, "folderId": 0})
with open('/tmp/grafana-payload.json', 'w') as f:
    f.write(payload)
print("Dashboard payload ready")
