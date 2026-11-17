import json
import tempfile
import unittest
from fractions import Fraction as F
from pathlib import Path
from archive.database import Database
from archive.reading import read_artifact, export_artifact
from archive.codec import encode_payload
from observations.service import save_readings
from cohorts.service import save_model, freeze_cohort
from analysis.service import analyze
from reports.service import make_report


def reading(identity, time, value, variance=0, rev=1, withdrawn=False):
    return {'measurement_id': identity, 'rev': rev, 'time': time, 'value': value,
            'variance': variance, 'unit': 'mm', 'time_unit': 'day', 'withdrawn': withdrawn}


def model(knots=(0, 1, 2, 3), innovations=None):
    if innovations is None:
        innovations = [[[0, 0], [0, 0]] for _ in range(len(knots) - 1)]
    return {'name': 'river', 'rev': 1, 'unit': 'mm', 'time_unit': 'day',
            'knots': list(knots), 'innovations': innovations}


def request(label, *terms):
    return {'label': label, 'terms': [list(p) for p in terms]}


def pipeline(db, rows, targets, requests, specification=None):
    model_id = save_model(db, specification or model())
    save_readings(db, rows)
    cohort_id = freeze_cohort(db, model_id, [(r['measurement_id'], r['rev']) for r in rows])
    analysis_id = analyze(db, cohort_id, targets)
    report_id = make_report(db, analysis_id, requests)
    return cohort_id, analysis_id, report_id


def result(db, report_id):
    return read_artifact(db, report_id)['payload']['result']


def counts(db):
    return tuple(db.connect().execute('SELECT count(*) FROM ' + name).fetchone()[0]
                 for name in ('revisions', 'heads', 'blobs', 'catalog', 'edges', 'models'))


def scenario(case_id, inputs, expected, actual, downstream_expected, downstream_actual,
             paths, oracle):
    def exact_json(value):
        if isinstance(value, (F, int)) and not isinstance(value, bool):
            return str(value)
        if isinstance(value, dict):
            return {key: exact_json(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [exact_json(item) for item in value]
        return value

    print('POINTWISE_SCENARIO ' + json.dumps(exact_json(
        {'case_id': case_id, 'input': inputs, 'expected': expected, 'actual': actual,
         'downstream_expected': downstream_expected, 'downstream_actual': downstream_actual,
         'code_paths': paths, 'oracle': oracle}), ensure_ascii=False, sort_keys=True))


class WorkflowCase(unittest.TestCase):
    def setUp(self):
        self.db = Database(':memory:')
        self.addCleanup(self.db.close)

    def straight(self, targets=(0, 1, 2)):
        return pipeline(self.db, [reading('a', 0, 2), reading('b', 1, 5)], targets,
                        [request('future', (2, 1))])


class TestWorkflow(WorkflowCase):
    def test_quality_decisions(self):
        _, _, report = pipeline(self.db, [reading('a', 0, 2)], [0, 1],
                                [request('now', (0, 1)), request('future', (1, 1))])
        data = result(self.db, report)
        decisions = ['schedule_measurement' if status == 'not_estimable' else 'use_estimate'
                     for status in data['statuses']]
        self.assertEqual(data['estimates'], [F(2), None])
        self.assertEqual(decisions, ['use_estimate', 'schedule_measurement'])
        scenario('v5', {'x(0)': 2}, [2, None], data['estimates'],
                 ['use_estimate', 'schedule_measurement'], decisions,
                 ['analysis/inference.py', 'analysis/identifiability.py', 'reports/contrasts.py'],
                 'One exact level leaves slope arbitrary; future level changes with slope.')

    def test_day_reopen(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'day.sqlite'
            with Database(path) as db:
                c, a, old = pipeline(db, [reading('a', 0, 2), reading('b', 1, 5)], [0, 1, 2],
                                     [request('future', (2, 1))])
                old_bundle = encode_payload(export_artifact(db, old))
                save_readings(db, [reading('b', 1, 6, rev=2)])
                mid = read_artifact(db, c)['payload']['model_id']
                fresh_c = freeze_cohort(db, mid, [('a', 1), ('b', 2)])
                fresh_a = analyze(db, fresh_c, [0, 1, 2])
                fresh = make_report(db, fresh_a, [request('future', (2, 1))])
                self.assertEqual(result(db, fresh)['estimates'], [F(10)])
                db.initialize()
            with Database(path) as reopened:
                self.assertEqual(encode_payload(export_artifact(reopened, old)), old_bundle)
                self.assertEqual(result(reopened, old)['estimates'], [F(8)])
                self.assertEqual(result(reopened, fresh)['estimates'], [F(10)])
                self.assertEqual(len(export_artifact(reopened, old)['lineage']), 4)
                scenario('v7.correction_snapshot', {'x(0)': 2, 'old_x(1)': 5, 'new_x(1)': 6},
                         [8, 10], [result(reopened, old)['estimates'][0],
                                   result(reopened, fresh)['estimates'][0]],
                         {'old_bundle_equal': True},
                         {'old_bundle_equal': encode_payload(export_artifact(reopened, old)) == old_bundle},
                         ['observations/service.py', 'cohorts/binding.py', 'analysis/service.py',
                          'reports/service.py', 'archive/reading.py', 'archive/exporting.py'],
                         'Exact straight line: 2*x(1)-x(0). Old canonical bundle equality asserted.')
