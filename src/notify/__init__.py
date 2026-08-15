"""Notification app — daily service health checks and weekly follower summary.

Runs as its own container service (see the `notify-daily` / `notify-weekly`
entries in docker-compose.yml), sending alerts via the Prowl webhook.
"""
