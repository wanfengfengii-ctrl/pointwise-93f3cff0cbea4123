import sys
import tempfile
from pathlib import Path
from fractions import Fraction as F
from archive.database import Database
from archive.reading import read_artifact, export_artifact, CorruptArtifact, UnknownArtifact
from archive.codec import encode_payload, decode_payload
from observations.service import save_readings
from cohorts.service import freeze_cohort
from analysis.service import analyze
from reports.service import make_report
from tests.test_workflow import WorkflowCase, reading, request, pipeline, result, counts


def abort_publication(stage, identity):
    if stage != 'after_payload' or not identity:
        raise AssertionError('wrong publication hook')
    raise RuntimeError('controlled publication failure')


class TestArchive(WorkflowCase):
    def test_correction_and_reopen(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'review.sqlite'
            with Database(path) as db:
                cohort, _, old = pipeline(db, [reading('a', 0, 2), reading('b', 1, 5)], [0, 1, 2],
                                         [request('future', (2, 1))])
                frozen = encode_payload(read_artifact(db, old))
                exported = encode_payload(export_artifact(db, old))
                save_readings(db, [reading('b', 1, 6, rev=2)])
                mid = read_artifact(db, cohort)['payload']['model_id']
                c2 = freeze_cohort(db, mid, [('a', 1), ('b', 2)])
                a2 = analyze(db, c2, [0, 1, 2])
                new = make_report(db, a2, [request('future', (2, 1))])
                self.assertEqual(result(db, new)['estimates'], [F(10)])
                before = counts(db)
                db.initialize()
                self.assertEqual(counts(db), before)
            with Database(path) as reopened:
                self.assertEqual(encode_payload(read_artifact(reopened, old)), frozen)
                self.assertEqual(encode_payload(export_artifact(reopened, old)), exported)
                self.assertEqual(result(reopened, old)['estimates'], [F(8)])
                self.assertEqual(result(reopened, new)['estimates'], [F(10)])
                self.assertEqual(read_artifact(reopened, c2)['payload']['members'][1]['rev'], 2)
                self.assertEqual(read_artifact(reopened, cohort)['payload']['members'][1]['rev'], 1)

    def test_report_publication_retry(self):
        _, analysis, old = self.straight()
        requests = [request('change', (2, 1), (0, -1))]
        before = counts(self.db)
        with self.assertRaisesRegex(RuntimeError, 'controlled publication'):
            make_report(self.db, analysis, requests, failure_hook=abort_publication)
        self.assertEqual(counts(self.db), before)
        report = make_report(self.db, analysis, requests)
        self.assertEqual(result(self.db, report)['estimates'], [F(6)])
        self.assertEqual(make_report(self.db, analysis, requests), report)
        self.assertEqual(counts(self.db)[2:5],
                         (before[2] + 1, before[3] + 1, before[4] + 1))
        self.assertEqual(result(self.db, old)['estimates'], [F(8)])
        self.assertEqual(len(export_artifact(self.db, report)['lineage']), 4)

    def test_analysis_rollback(self):
        cohort, _, _ = self.straight()
        before = counts(self.db)
        with self.assertRaisesRegex(RuntimeError, 'controlled publication'):
            analyze(self.db, cohort, [0, 2], failure_hook=abort_publication)
        self.assertEqual(counts(self.db), before)
        analysis = analyze(self.db, cohort, [0, 2])
        report = make_report(self.db, analysis, [request('future', (2, 1))])
        self.assertEqual(result(self.db, report)['estimates'], [F(8)])

    def test_fixed_export_without_inference(self):
        _, _, identity = self.straight()
        previous_profile = sys.getprofile()

        def forbid_inference(frame, event, arg):
            if event == 'call' and frame.f_code.co_name == 'infer_joint_trajectory':
                raise AssertionError('fixed reads must not infer')

        try:
            sys.setprofile(forbid_inference)
            first = encode_payload(export_artifact(self.db, identity))
            node = read_artifact(self.db, identity)
            node['payload']['result']['estimates'][0] = -1
            self.assertEqual(encode_payload(export_artifact(self.db, identity)), first)
        finally:
            sys.setprofile(previous_profile)
        bundle = decode_payload(first)
        self.assertEqual(bundle['model']['unit'], 'mm')
        self.assertEqual([r['measurement_id'] for r in bundle['observations']], ['a', 'b'])
        self.assertEqual(bundle['result']['estimates'], [F(8)])
        self.assertEqual([n['kind'] for n in bundle['lineage']], ['model', 'cohort', 'analysis', 'report'])
        with self.assertRaises(UnknownArtifact):
            read_artifact(self.db, 'missing')

    def test_corrupt_export_rejected(self):
        _, _, identity = self.straight()
        c = self.db.connect()
        saved = c.execute('SELECT body FROM blobs WHERE id=?', (identity,)).fetchone()[0]
        c.execute('UPDATE blobs SET body=? WHERE id=?', ('{}', identity))
        with self.assertRaises(CorruptArtifact):
            export_artifact(self.db, identity)
        c.execute('UPDATE blobs SET body=? WHERE id=?', (saved, identity))
        parent = c.execute('SELECT parent FROM edges WHERE child=?', (identity,)).fetchone()[0]
        c.execute('DELETE FROM edges WHERE child=?', (identity,))
        with self.assertRaises(CorruptArtifact):
            export_artifact(self.db, identity)
        c.execute('INSERT INTO edges VALUES (?,?,?)', (identity, 0, parent))
        self.assertEqual(result(self.db, identity)['estimates'], [F(8)])
        c.execute('UPDATE catalog SET kind=? WHERE id=?', ('cohort', identity))
        with self.assertRaises(CorruptArtifact):
            export_artifact(self.db, identity)

    def test_codec_and_schema(self):
        text = encode_payload({'values': [F(-2, 3), None, F(0)]})
        self.assertEqual(decode_payload(text), {'values': [F(-2, 3), None, F(0)]})
        for bad in ('{"$fraction":[2,4]}', '{"$fraction":[1,0]}', '{"x":0.5}'):
            with self.assertRaises(ValueError):
                decode_payload(bad)
        self.db.connect().execute('PRAGMA user_version=2')
        with self.assertRaises(ValueError):
            self.db.initialize()
        self.db.connect().execute('PRAGMA user_version=1')
