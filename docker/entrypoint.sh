#!/bin/bash
set -e

# First run: seed a starting config from the template so the dashboard has
# sensible defaults instead of an empty form. Left alone on later runs so
# whatever the user already saved through the dashboard isn't overwritten.
if [ ! -f /app/config.json ]; then
    cp /app/config.example.json /app/config.json
fi

exec /usr/bin/supervisord -n -c /etc/supervisor/conf.d/supervisord.conf
