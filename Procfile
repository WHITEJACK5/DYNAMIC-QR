web: gunicorn wsgi:application --bind 127.0.0.1:${PORT:-5000} --workers ${WEB_CONCURRENCY:-4} --access-logfile - --error-logfile -
worker: python -m rq worker nare --url ${REDIS_URL}
release: python -m scripts.pgbackup verify
