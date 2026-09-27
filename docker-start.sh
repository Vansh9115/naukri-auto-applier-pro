#!/bin/bash
# Run this instead of `docker compose up` directly.
#
# Docker silently creates a bind-mounted host path as a *directory* if it
# doesn't already exist when the container starts — which would turn
# config.json/applied_jobs.csv into folders instead of files and break the
# app. This makes sure they exist as real (possibly empty) files first.
set -e
cd "$(dirname "$0")"

mkdir -p docker-data/uploads docker-data/naukri_chrome_profile
touch docker-data/config.json docker-data/applied_jobs.csv

docker compose up --build
