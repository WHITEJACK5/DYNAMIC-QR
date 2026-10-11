# Binds 0.0.0.0, not 127.0.0.1: a platform-managed web dyno is reached
# through the platform's own router, not a reverse proxy you run alongside it,
# so a loopback bind leaves the port unreachable and the dyno never becomes
# healthy. Behind your own nginx, override with -b 127.0.0.1:$PORT.
web: gunicorn wsgi:application --bind 0.0.0.0:${PORT:-5000} --workers ${WEB_CONCURRENCY:-4} --access-logfile - --error-logfile -
# `rq worker`, not `python -m rq worker`: rq ships no __main__, so
# `python -m rq` exits immediately with "No module named rq.__main__".
worker: rq worker DR --url ${REDIS_URL}
release: python -m scripts.pgbackup verify
