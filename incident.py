"""Public business regression for the monitoring trajectory incident."""
import argparse
import json
import tempfile
import unittest
from fractions import Fraction as F
from pathlib import Path
from archive.database import Database
from archive.codec import encode_payload
from archive.reading import read_artifact
from analysis.constraints import ExactInconsistency
from analysis.service import analyze
from cohorts.service import save_model, freeze_cohort
from observations.service import save_readings
from reports.service import make_report


def reading(identity, time, value, variance=0):
    return dict(measurement_id=identity, rev=1, time=time, value=value,
                variance=variance, unit='mm', time_unit='day')


def model(knots, innovations):
    return dict(name='incident', rev=1, unit='mm', time_unit='day',
                knots=knots, innovations=innovations)


def request(label, *terms):
    return dict(label=label, terms=[list(pair) for pair in terms])


def prepare(db, specification, rows):
    mid = save_model(db, specification)
    save_readings(db, rows)
    return freeze_cohort(db, mid, [(row['measurement_id'], row['rev']) for row in rows])


def result(db, identity):
    return read_artifact(db, identity)['payload']['result']


def emit(case, expected, actual):
    record = dict(case=case, expected=expected, actual=actual, matches=expected == actual)
    print('TRAJECTORY_CASE ' + encode_payload(record))
    return expected == actual


def diffuse_case():
    with Database(':memory:') as db:
        cid = prepare(db, model([0, 1, 2], [[[0, 0], [0, 0]]] * 2),
                      [reading('a', 0, 2)])
        aid = analyze(db, cid, [0, 1, 2])
        rid = make_report(db, aid, [
            request('now', (0, 1)), request('future', (1, 1)),
            request('curvature', (2, 1), (1, -2), (0, 1))])
        data = result(db, rid)
        actual = {key: data[key] for key in ('statuses', 'estimates', 'covariance')}
        expected = dict(statuses=['estimable', 'not_estimable', 'estimable'],
                        estimates=[F(2), None, F(0)],
                        covariance=[[F(0), None, F(0)],
                                    [None, None, None], [F(0), None, F(0)]])
        return emit('unknown_initial_drift', expected, actual)


def conflict_case():
    with Database(':memory:') as db:
        cid = prepare(db, model([0, 1, 2], [[[0, 0], [0, 0]]] * 2),
                      [reading('a', 1, 5), reading('b', 1, 6)])
        before = tuple(db.connect().iterdump())
        rejected = False
        try:
            analyze(db, cid, [1, 2])
        except ExactInconsistency:
            rejected = True
        actual = dict(rejected=rejected, unchanged=tuple(db.connect().iterdump()) == before)
        return emit('conflicting_exact_levels',
                    dict(rejected=True, unchanged=True), actual)


def shared_case():
    with Database(':memory:') as db:
        specification = model([0, 1, 2, 3],
                              [[[0, 0], [0, 0]], [[1, 0], [0, 0]], [[1, 0], [0, 0]]])
        cid = prepare(db, specification, [reading('a', 0, 2), reading('b', 1, 5)])
        aid = analyze(db, cid, [1, 2, 3])
        rid = make_report(db, aid, [
            request('two', (2, 1)), request('three', (3, 1)),
            request('difference', (3, 1), (2, -1)),
            request('cumulative', (2, 1), (3, 1), (1, -2))])
        data = result(db, rid)
        actual = dict(trajectory_covariance=read_artifact(db, aid)['payload']['trajectory']['covariance'],
                      estimates=data['estimates'], covariance=data['covariance'],
                      statuses=data['statuses'])
        expected = dict(trajectory_covariance=[[0, 0, 0], [0, 1, 1], [0, 1, 2]],
                        estimates=[8, 11, 3, 9],
                        covariance=[[1, 1, 0, 2], [1, 2, 1, 3], [0, 1, 1, 1], [2, 3, 1, 5]],
                        statuses=['estimable'] * 4)
        return emit('shared_future_errors', expected, actual)


CASES = dict(diffuse=diffuse_case, conflict=conflict_case, shared=shared_case)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=tuple(CASES))
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args(argv)
    original_ok = True
    if args.verify:
        suite = unittest.defaultTestLoader.discover('tests', top_level_dir='.')
        original_ok = unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
    if args.demo:
        from archive.exporting import run_demo
        with tempfile.TemporaryDirectory(prefix='trajectory-demo-') as directory:
            run_demo('samples/day.json', Path(directory) / 'day.sqlite')
    selected = [CASES[args.case]] if args.case else list(CASES.values())
    business_ok = all([check() for check in selected])
    if not business_ok:
        print('JOINT_TRAJECTORY_MISMATCH')
    else:
        print('JOINT_TRAJECTORY_OK')
    return 0 if business_ok and original_ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
