Worker code is packaged with the API to share schemas and avoid incompatible copies.

Run `celery -A xek.jobs:celery worker --concurrency=1 --loglevel=INFO` on Linux/Docker.
Run one separate `celery -A xek.jobs:celery beat --loglevel=INFO` scheduler.
One worker slot limits heavy model/render jobs. Run additional workers only after allocating GPUs.
Inline development mode is single-process and cannot survive interpreter termination mid-job;
set affected running jobs to failed in the database after verifying no worker is executing them.
