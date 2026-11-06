"""Fixed ORM fixture for a newly created, explicitly owned performance DB."""
import json
import os
import re
import sys
from datetime import date
from decimal import Decimal

from perf import fixtures as f


def guard(run_id, database):
    if (not re.fullmatch(r"[a-f0-9]{3,32}", run_id)
            or database["NAME"] != "perf_" + run_id
            or database["HOST"] != "perf_" + run_id + "_db"):
        raise ValueError("not an isolated performance database")


def execute(mode, scenario):
    import django

    django.setup()
    from django.conf import settings
    from django.contrib.auth.hashers import make_password
    from django.db import connection, transaction

    from accounts.models import User
    from social.models import Comment, CommentIdentity, Follow, Like
    from workouts.models import Post, PostIdentity, WorkoutExercise, WorkoutSet

    guard(os.environ["PERF_RUN_ID"], settings.DATABASES["default"])
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database()")
        if cursor.fetchone()[0] != settings.DATABASES["default"]["NAME"]:
            raise ValueError("connection identity mismatch")
    exercises, sets = f.dimensions(scenario)
    if mode == "seed":
        if any(model.objects.exists() for model in (User, PostIdentity, CommentIdentity, Follow)):
            raise ValueError("fixture requires an empty database")
        with transaction.atomic():
            users = [User(id=f.user_id(a), username=f.username(a),
                          email=f"{f.username(a)}@fitlog-perf.invalid", display_name=f"性能試験 {a}",
                          date_joined=f.timestamp(a), password=make_password(f.PASSWORD)) for a in range(5)]
            User.objects.bulk_create(users)
            PostIdentity.objects.bulk_create([PostIdentity(id=f.post_id(i), author_id=f.user_id(i % 5))
                                               for i in range(1000)])
            Post.objects.bulk_create([Post(identity_id=f.post_id(i), user_id=f.user_id(i % 5),
                                           performed_on=date(2026, 1, 1), note="固定性能試験",
                                           created_at=f.timestamp(i), updated_at=f.timestamp(i))
                                      for i in range(1000)])
            ex_rows = [WorkoutExercise(id=f.identity("exercise", i * 10 + e),
                                      post_id=f.post_id(i), position=e, name=f"Exercise {e}")
                       for i in range(1000) for e in range(exercises)]
            WorkoutExercise.objects.bulk_create(ex_rows, batch_size=1000)
            # At most 20,000 in-memory rows; total bounded to 200,000.
            for start in range(0, len(ex_rows), 1000):
                WorkoutSet.objects.bulk_create([
                    WorkoutSet(id=f.identity("set", (start + j) * 20 + s), exercise=ex,
                               position=s, weight_kg=Decimal("60.00"), reps=10)
                    for j, ex in enumerate(ex_rows[start:start + 1000]) for s in range(sets)],
                    batch_size=1000)
            CommentIdentity.objects.bulk_create([
                CommentIdentity(id=f.identity("comment", i * 2 + c),
                                author_id=f.user_id((i % 5 + c + 1) % 5), post_uuid=f.post_id(i))
                for i in range(1000) for c in range(2)])
            Comment.objects.bulk_create([
                Comment(identity_id=f.identity("comment", i * 2 + c), post_id=f.post_id(i),
                        user_id=f.user_id((i % 5 + c + 1) % 5), body="固定コメント",
                        created_at=f.timestamp(i), updated_at=f.timestamp(i))
                for i in range(1000) for c in range(2)])
            Like.objects.bulk_create([Like(post_id=f.post_id(i), user_id=f.user_id((i % 5 + c + 1) % 5))
                                      for i in range(1000) for c in range(2)])
            Follow.objects.bulk_create([Follow(follower_id=f.user_id(a), followee_id=f.user_id((a + d) % 5))
                                        for a in range(5) for d in (1, 2)])
    counts = {"users": User.objects.count(), "posts": Post.objects.count(),
              "exercises": WorkoutExercise.objects.count(), "sets": WorkoutSet.objects.count(),
              "comments": Comment.objects.count(), "likes": Like.objects.count(), "follows": Follow.objects.count(),
              "posts_per_user": [Post.objects.filter(user_id=f.user_id(a)).count() for a in range(5)]}
    expected_likes = 2005 if mode == "audit-load" else 2000
    if counts != {"users": 5, "posts": 1000, "exercises": 1000 * exercises,
                  "sets": 1000 * exercises * sets, "comments": 2000, "likes": expected_likes,
                  "follows": 10, "posts_per_user": [200] * 5}:
        raise ValueError("fixture count audit failed")
    return counts


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in {"seed", "audit", "audit-load"}:
        raise SystemExit("seed|audit|audit-load normal|boundary")
    print(json.dumps(execute(sys.argv[1], sys.argv[2])))
