from archive.codec import encode_payload
from observations.service import save_readings
from observations.repository import ReadingRepository
from observations.revisions import RevisionConflict
from observations.validation import InvalidReading
from cohorts.service import save_model, freeze_cohort
from cohorts.selection import InvalidSelection
from tests.test_workflow import WorkflowCase, reading, model, counts


class TestReadings(WorkflowCase):
    def test_conflicting_revision_atomic(self):
        save_readings(self.db, [reading('a', 0, 2), reading('b', 1, 5)])
        before = list(self.db.connect().iterdump())
        with self.assertRaises(RevisionConflict):
            save_readings(self.db, [reading('a', 0, 3, rev=2), reading('b', 1, 6)])
        self.assertEqual(list(self.db.connect().iterdump()), before)

    def test_revision_replay(self):
        first = reading('a', 0, 2)
        save_readings(self.db, [first])
        save_readings(self.db, [reading('a', 0, 4, rev=3)])
        before = counts(self.db)
        response = save_readings(self.db, [first, reading('a', 0, 3, rev=2), first])
        self.assertEqual(response['accepted'], [])
        self.assertEqual(counts(self.db), before)
        self.assertEqual(ReadingRepository(self.db.connect()).get_heads(), {'a': 3})
        self.assertEqual(ReadingRepository(self.db.connect()).get_revision('a', 1).value, 2)
        with self.assertRaises(RevisionConflict):
            save_readings(self.db, [reading('b', 1, 4), reading('b', 1, 5)])
        self.assertEqual(counts(self.db), before)
        with self.assertRaises(RevisionConflict):
            save_readings(self.db, [reading('a', 0, 99)])
        self.assertEqual(counts(self.db), before)

    def test_withdrawal(self):
        mid = save_model(self.db, model())
        save_readings(self.db, [reading('a', 0, 2)])
        save_readings(self.db, [reading('a', 0, None, rev=2, withdrawn=True)])
        repo = ReadingRepository(self.db.connect())
        self.assertTrue(repo.get_revision('a', 2).withdrawn)
        self.assertEqual(repo.get_revision('a', 1).value, 2)
        before = counts(self.db)
        with self.assertRaises(InvalidSelection):
            freeze_cohort(self.db, mid, [('a', 2)])
        self.assertEqual(counts(self.db), before)
        freeze_cohort(self.db, mid, [('a', 1)])

    def test_invalid_batch_is_atomic(self):
        save_readings(self.db, [reading('a', 0, 2)])
        before = counts(self.db)
        for bad in (reading('b', 1, 3, variance=-1), reading('b', True, 3),
                    reading('b', 1, 1.5), reading('b', 1, 3, rev=True)):
            with self.assertRaises(InvalidReading):
                save_readings(self.db, [reading('a', 0, 9, rev=2), bad])
            self.assertEqual(counts(self.db), before)
        self.assertEqual(encode_payload({'f': ReadingRepository(self.db.connect()).get_revision('a', 1).time}),
                         '{"f":{"$fraction":[0,1]}}')
