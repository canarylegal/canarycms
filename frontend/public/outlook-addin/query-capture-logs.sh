#!/bin/bash
set -e
echo "=== Capture log table ==="
docker exec canary-db psql -U canary -d canary -c "\dt *capture*" 2>/dev/null || true
echo ""
echo "=== Recent send-capture logs ==="
docker exec canary-db psql -U canary -d canary -c \
  "SELECT created_at, step, left(coalesce(detail,''),120) AS detail, case_id
   FROM outlook_plugin_send_capture_log
   ORDER BY created_at DESC LIMIT 25;" 2>/dev/null \
|| docker exec canary-db psql -U postgres -d canary -c \
  "SELECT created_at, step, left(coalesce(detail,''),120) AS detail, case_id
   FROM outlook_plugin_send_capture_log
   ORDER BY created_at DESC LIMIT 25;" 2>/dev/null \
|| echo "Run: docker exec canary-db psql -U canary -d canary -c \"\\dt\""
