from observations.validation import validate_reading_batch
from observations.revisions import plan_revisions
from observations.repository import ReadingRepository


def save_readings(db, batch):
    incoming = validate_reading_batch(batch)
    with db.transaction() as c:
        repository = ReadingRepository(c)
        existing = {}
        for item in incoming:
            try:
                existing[item.identity] = repository.get_revision(*item.identity)
            except KeyError:
                pass
        plan = plan_revisions(incoming, existing, repository.get_heads())
        repository.apply_plan(plan)
        result = {'accepted': [item.identity for item in plan.accepted],
                  'ignored': list(plan.ignored)}
    return result
