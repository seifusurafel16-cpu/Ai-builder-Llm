# Procfile — optional multi-process deployment.
#
# By default Railway builds a single Docker image and runs the web process below,
# which also runs the inline training worker (RUN_INLINE_WORKER=true). This is the
# simplest one-service setup.
#
# To scale training separately:
#   1. Set RUN_INLINE_WORKER=false on the web service.
#   2. Add a Railway service from the same image using the `worker` command:
#        python -m apps.api.worker
#   3. The worker shares the same DATABASE_URL so it picks up the same job queue.

web: sh -c "python -m uvicorn apps.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"
worker: python -m apps.api.worker
