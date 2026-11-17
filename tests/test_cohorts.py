from fractions import Fraction as F
from cohorts.service import save_model, freeze_cohort
from cohorts.models import InvalidModel
from cohorts.selection import InvalidSelection
from observations.service import save_readings
from archive.reading import read_artifact
from tests.test_workflow import WorkflowCase, reading, model, counts


class TestCohorts(WorkflowCase):
    def test_missing_and_same_time(self):
        mid = save_model(self.db, model())
        rows = [reading('missing', '1/2', None, 2),
                reading('one', 1, 5, 1), reading('two', 1, 6, 3)]
        save_readings(self.db, rows)
        identity = freeze_cohort(self.db, mid, [('two', 1), ('missing', 1), ('one', 1)])
        payload = read_artifact(self.db, identity)['payload']
        members = payload['members']
        self.assertEqual([r['measurement_id'] for r in members], ['two', 'missing', 'one'])
        self.assertEqual([r['value'] for r in members], [F(6), None, F(5)])
        self.assertEqual([r['variance'] for r in members], [F(3), F(2), F(1)])
        self.assertEqual(members[1]['time'], F(1, 2))
        rows[0]['value'] = 99
        payload['members'][0]['value'] = -100
        self.assertEqual(read_artifact(self.db, identity)['payload']['members'][0]['value'], 6)
        self.assertIsNone(read_artifact(self.db, identity)['payload']['members'][1]['value'])

    def test_model_validation(self):
        singular = model((0, 1), [[[1, 1], [1, 1]]])
        mid = save_model(self.db, singular)
        self.assertEqual(save_model(self.db, singular), mid)
        before = counts(self.db)
        for q in ([[1, 2], [2, 1]], [[0, 1], [1, 1]], [[1, 0, 0], [0, 1, 0]],
                  [[1, 1], [0, 1]]):
            with self.assertRaises(InvalidModel):
                save_model(self.db, model((0, 1), [q]))
            self.assertEqual(counts(self.db), before)
        conflict = model((0, 1))
        with self.assertRaises(InvalidModel):
            save_model(self.db, conflict)
        self.assertEqual(counts(self.db), before)
        save_readings(self.db, [dict(reading('a', 0, 2), unit='cm')])
        before = counts(self.db)
        with self.assertRaises(InvalidSelection):
            freeze_cohort(self.db, mid, [('a', 1)])
        self.assertEqual(counts(self.db), before)

    def test_selection_guards(self):
        mid = save_model(self.db, model())
        save_readings(self.db, [reading('a', 0, 2), reading('b', 1, None, rev=2, withdrawn=True)])
        before = counts(self.db)
        for members in ([('unknown', 1)], [('a', 1), ('a', 1)],
                        [('a', 1), ('a', 2)], [('b', 2)], [('a', True)]):
            with self.assertRaises(InvalidSelection):
                freeze_cohort(self.db, mid, members)
            self.assertEqual(counts(self.db), before)

    def test_limits_and_model_coverage(self):
        mid = save_model(self.db, model((0, 30)))
        rows = [reading(str(i), i, None) for i in range(25)]
        save_readings(self.db, rows)
        before = counts(self.db)
        with self.assertRaises(InvalidSelection):
            freeze_cohort(self.db, mid, [(str(i), 1) for i in range(25)])
        self.assertEqual(counts(self.db), before)
        save_readings(self.db, [reading('outside', 31, 0)])
        with self.assertRaises(InvalidSelection):
            freeze_cohort(self.db, mid, [('outside', 1)])
