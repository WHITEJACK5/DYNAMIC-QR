web: gunicorn wsgi:application --bind 127.0.0.1:${PORT:-5000} --workers ${WEB_CONCURRENCY:-4} --access-logfile - --error-logfile -
# `rq worker`, not `python -m rq worker`: rq ships no __main__, so
# `python -m rq` exits immediately with "No module named rq.__main__".
worker: rq worker nare --url ${REDIS_URL}
release: python -m scripts.pgbackup verify
