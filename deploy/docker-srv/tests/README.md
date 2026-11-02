# Isolated queue pause exercise

Run from the repository root on the Mac.
Use a disposable container. Do not run this fixture in the live application.
The container has no network, NAS mount, or production credentials.
The exercise uses SQLite and the application's real ORM queue.

```bash
image=registry.my.3simbio.ru/librephotos/app:20261101T202714Z-eadec7938a90
name=librephotos-pause-exercise
docker run -d --rm --name "$name" --network none --memory 768m \
  -e BASE_DATA=/tmp/pause-test-data -e BASE_LOGS=/tmp/pause-test-logs \
  -e SECRET_KEY=isolated-pause-test-key \
  -e DJANGO_SETTINGS_MODULE=pause_test_settings -e PYTHONPATH=/tmp:/code \
  -e NO_COVERAGE=1 --entrypoint sh "$image" -c 'tail -f /dev/null'
trap 'docker stop "$name" >/dev/null' EXIT
docker cp deploy/docker-srv/scan_checkpoint.py "$name":/tmp/scan_checkpoint.py
for file in pause_test_settings.py pause_test_tasks.py test_pause_workflow.py; do
  docker cp "deploy/docker-srv/tests/$file" "$name":/tmp/
done
docker exec -w /code "$name" python /tmp/test_pause_workflow.py scan
docker exec -w /code "$name" python /tmp/test_pause_workflow.py tags
```

Expected result: `isolated_pause_resume_passed` is `true`.
The same job completes all 20 tasks after a partial pause.
Completed tasks plus remaining tasks equal 20 at the pause.
The log confirms that workers recycled during the exercise.
