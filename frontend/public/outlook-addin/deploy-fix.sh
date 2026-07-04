#!/bin/bash
LIVE_DIR="/opt/canarycms/frontend/public/outlook-addin"
FILES="commands-launch.js commands.js commands.html manifest.xml outlook-shared.js compose-apply.js compose-handoff-poll.js send-upload-queue.js compose-pane.html compose-pane.js taskpane.html query-capture-logs.sh"

echo "=== Host path: $LIVE_DIR ==="
if [ -f "$LIVE_DIR/manifest.xml" ]; then
  sed -n 's/.*<Version>\([^<]*\)<\/Version>.*/\1/p' "$LIVE_DIR/manifest.xml" | head -1
  ls -la "$LIVE_DIR/commands-launch.js" 2>/dev/null || echo "(no commands-launch.js yet)"
else
  echo "ERROR: $LIVE_DIR not found"
  exit 1
fi

echo ""
echo "=== Docker containers ==="
docker ps --format '{{.Names}}' 2>/dev/null || true

DOCKER_COPIED=0
for n in $(docker ps --format '{{.Names}}' 2>/dev/null); do
  echo "$n" | grep -Eiq 'canary|frontend|nginx|web' || continue
  echo ""
  echo "--- checking $n ---"
  for p in \
    /usr/share/nginx/html/outlook-addin \
    /app/dist/outlook-addin \
    /var/www/html/outlook-addin \
    /usr/share/nginx/html \
    ; do
    if docker exec "$n" test -f "$p/manifest.xml" 2>/dev/null; then
      echo "Found manifest at $n:$p/manifest.xml"
      echo "Before:" $(docker exec "$n" sed -n 's/.*<Version>\([^<]*\)<\/Version>.*/\1/p' "$p/manifest.xml" | head -1)
      for f in $FILES; do
        docker cp "$LIVE_DIR/$f" "$n:$p/$f"
      done
      echo "After:" $(docker exec "$n" sed -n 's/.*<Version>\([^<]*\)<\/Version>.*/\1/p' "$p/manifest.xml" | head -1)
      docker exec "$n" ls -la "$p/commands-launch.js" 2>/dev/null || true
      DOCKER_COPIED=1
    fi
  done
done

echo ""
echo "=== nginx config ==="
grep -rh outlook-addin /etc/nginx/ 2>/dev/null | head -10 || true

if [ "$DOCKER_COPIED" -eq 0 ]; then
  echo ""
  echo "WARN: no docker outlook-addin path found; checking bind mounts..."
  for n in $(docker ps --format '{{.Names}}' 2>/dev/null); do
    echo "$n" | grep -Eiq 'canary|frontend|nginx|web' || continue
    docker inspect "$n" --format '{{.Name}} mounts={{range .Mounts}}{{.Source}}->{{.Destination}} {{end}}' 2>/dev/null
  done
fi

echo ""
echo "Host manifest now:" $(sed -n 's/.*<Version>\([^<]*\)<\/Version>.*/\1/p' "$LIVE_DIR/manifest.xml" | head -1)
echo "Done."
