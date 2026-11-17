"""Independent audit for the joint trajectory / change-report repair.

Every expectation below is produced without calling the production inference
entry points: exact straight lines use the two-point formula, shared
innovations are expanded by hand from their coefficients, and the noisy
non-degenerate case uses a self-contained augmented BLUE elimination plus a
marginal likelihood argument. Only the public persistence and report services
are exercised, mirroring how an analyst actually consumes the archive.
"""
import unittest
from fractions import Fraction as F
from analysis.service import analyze
from analysis.constraints import ExactInconsistency
from analysis.representation import JointTrajectory
from cohorts.service import save_model, freeze_cohort
from observations.service import save_readings
from reports.service import make_report
from archive.database import Database
from archive.reading import read_artifact
from tests.test_workflow import WorkflowCase, reading, model, request, result, counts


def _gauss_jordan(matrix, rhs):
    # Independent dense rational elimination oracle (no production algebra).
    rows = [[F(x) for x in row] + [F(y)] for row, y in zip(matrix, rhs)]
    rank = 0
    for column in range(len(rows[0]) - 1):
        pivot = next((i for i in range(rank, len(rows)) if rows[i][column]), None)
        if pivot is None:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        divisor = rows[rank][column]
        rows[rank] = [value / divisor for value in rows[rank]]
        for i in range(len(rows)):
            if i != rank and rows[i][column]:
                multiplier = rows[i][column]
                rows[i] = [a - multiplier * b for a, b in zip(rows[i], rows[rank])]
        rank += 1
    return [row[-1] for row in rows]


def marginal_blue(rows, targets, specification):
    """Augmented BLUE on the marginal observation covariance (independent)."""
    rows = [row for row in rows if row['value'] is not None]
    times = [F(row['time']) for row in rows]
    origin = F(specification['knots'][0])

    def process_cov(t, s):
        total = F(0)
        for end, q in zip(specification['knots'][1:], specification['innovations']):
            end = F(end)
            if end <= min(t, s):
                left, right = (F(1), t - end), (F(1), s - end)
                total += sum(left[i] * F(q[i][j]) * right[j]
                             for i in range(2) for j in range(2))
        return total

    size = len(rows)
    v = [[process_cov(t, s) + (F(rows[i]['variance']) if i == j else 0)
          for j, s in enumerate(times)] for i, t in enumerate(times)]
    system = [v[i] + [F(1), times[i] - origin] for i in range(size)]
    system += [[F(1)] * size + [F(0), F(0)],
               [t - origin for t in times] + [F(0), F(0)]]
    weights, means = [], []
    for t in targets:
        w = _gauss_jordan(system, [process_cov(t, s) for s in times] + [1, t - origin])[:size]
        weights.append(w)
        means.append(sum(wi * F(row['value']) for wi, row in zip(w, rows)))
    covariance = []
    for i, t in enumerate(targets):
        line = []
        for j, s in enumerate(targets):
            value = process_cov(t, s)
            value -= sum(weights[i][k] * process_cov(times[k], s) for k in range(size))
            value -= sum(weights[j][k] * process_cov(t, times[k]) for k in range(size))
            value += sum(weights[i][k] * v[k][l] * weights[j][l]
                         for k in range(size) for l in range(size))
            line.append(value)
        covariance.append(line)
    return means, covariance


class TestIndependentRepairAudit(WorkflowCase):
    # ---- normal inputs: exact and noisy, with hand-derived expectations ----

    def test_straight_line_two_point_formula(self):
        # Exact readings pin x(0)=2 and x(1)=5, so the line part is the
        # two-point formula x(t)=2+3t: x(2)=8 and change=6. The rank-one
        # innovation at t=2 adds one unit-variance level coordinate w to every
        # downstream level, so both requested combinations carry error w and
        # share covariance 1; the zero-innovation first interval adds nothing.
        rows = [reading('a', 0, 2), reading('b', 1, 5)]
        specification = model((0, 1, 2), [[[0, 0], [0, 0]], [[1, 1], [1, 1]]])
        _, analysis, report_id = self._build(rows, [0, 1, 2],
                                             [request('future', (2, 1)),
                                              request('change', (2, 1), (0, -1))],
                                             specification)
        data = result(self.db, report_id)
        self.assertEqual(data['estimates'], [F(8), F(6)])
        self.assertEqual(data['covariance'], [[F(1), F(1)], [F(1), F(1)]])
        trajectory = JointTrajectory.from_payload(
            read_artifact(self.db, analysis)['payload']['trajectory'])
        self.assertEqual(trajectory.unknown_directions, ())
        self.assertEqual(trajectory.estimates, (F(2), F(5), F(8)))

    def test_weighted_least_squares_hand_covariance(self):
        # No process noise: deterministic line, two noisy readings with
        # variances 1 and 3 at t=0 and t=2. Hand WLS gives level 2, slope 2;
        # the level estimate at t=1 has variance 1 and the t=2 level 3,
        # with shared cross variance 3/2.
        specification = model((0, 1, 2), [[[0, 0], [0, 0]], [[0, 0], [0, 0]]])
        rows = [reading('a', 0, 2, 1), reading('b', 2, 6, 3)]
        _, _, report_id = self._build(rows, [0, 1, 2],
                                      [request('x1', (1, 1)), request('x2', (2, 1))],
                                      specification)
        data = result(self.db, report_id)
        self.assertEqual(data['estimates'], [F(4), F(6)])
        self.assertEqual(data['covariance'], [[F(1), F(3, 2)], [F(3, 2), F(3)]])

    def test_noisy_non_degenerate_matches_marginal_blue(self):
        specification = model((0, 1, 2, 3),
                              [[[1, '1/2'], ['1/2', 1]],
                               [[0, 0], [0, 0]], [[1, 0], [0, 0]]])
        rows = [reading('a', 0, 2, 1), reading('b', '3/2', 7, 2),
                reading('c', '3/2', 6, 3), reading('d', 2, 9, 1),
                reading('missing', '1/2', None)]
        targets = [F(0), F(3, 2), F(5, 2), F(3)]
        expected_mean, expected_cov = marginal_blue(rows, targets, specification)
        _, analysis, report_id = self._build(
            rows, targets, [request(str(t), (t, 1)) for t in targets], specification)
        data = result(self.db, report_id)
        self.assertEqual(data['estimates'], expected_mean)
        self.assertEqual(data['covariance'], expected_cov)
        trajectory = JointTrajectory.from_payload(
            read_artifact(self.db, analysis)['payload']['trajectory'])
        self.assertEqual(trajectory.unknown_directions, ())
        # Every persisted number stays an exact Fraction; no float anywhere.
        for cell in (x for line in data['covariance'] for x in line):
            self.assertIsInstance(cell, F)

    # ---- degenerate boundaries: diffuse fixed parameters and exact data ----

    def test_diffuse_initial_drift_masks_only_unidentifiable_contrast(self):
        rows = [reading('a', 0, 2)]
        _, analysis, _ = self._build(rows, [0, 1, 2], [], model((0, 1, 2)))
        report_id = make_report(self.db, analysis, [
            request('now', (0, 1)), request('future', (1, 1)),
            request('curvature', (2, 1), (1, -2), (0, 1))])
        data = result(self.db, report_id)
        self.assertEqual(data['statuses'], ['estimable', 'not_estimable', 'estimable'])
        self.assertEqual(data['estimates'], [F(2), None, F(0)])
        self.assertEqual(data['covariance'],
                         [[F(0), None, F(0)], [None, None, None], [F(0), None, F(0)]])

    def test_conflicting_exact_readings_reject_without_residue(self):
        mid = save_model(self.db, model())
        save_readings(self.db, [reading('a', 1, 5), reading('b', 1, 6)])
        cohort = freeze_cohort(self.db, mid, [('a', 1), ('b', 1)])
        before = counts(self.db)
        with self.assertRaises(ExactInconsistency):
            analyze(self.db, cohort, [1, 2])
        self.assertEqual(counts(self.db), before)

    def test_exact_reading_dominates_redundant_noisy_same_time_source(self):
        specification = model((0, 1), [[[0, 0], [0, 0]]])
        mid = save_model(self.db, specification)
        save_readings(self.db, [reading('p', 1, 5, 0), reading('q', 1, 7, 4)])
        cohort = freeze_cohort(self.db, mid, [('p', 1), ('q', 1)])
        analysis = analyze(self.db, cohort, [1])
        data = result(self.db, make_report(self.db, analysis, [request('x1', (1, 1))]))
        self.assertEqual(data['estimates'], [F(5)])
        self.assertEqual(data['covariance'], [[F(0)]])

    def test_singular_innovation_shared_level_error(self):
        # Q at t=2 is rank one: a single innovation along (1,1). It shifts the
        # t=2 level by a unit-variance coordinate w. Both x(2) and the change
        # x(2)-x(1) inherit that same error w, so every covariance entry among
        # them is 1; x(2)=8 and the change are 3 by the exact line.
        specification = model((0, 1, 2), [[[0, 0], [0, 0]], [[1, 1], [1, 1]]])
        rows = [reading('a', 0, 2), reading('b', 1, 5)]
        _, _, report_id = self._build(
            rows, [1, 2], [request('x2', (2, 1)), request('change', (2, 1), (1, -1))],
            specification)
        data = result(self.db, report_id)
        self.assertEqual(data['estimates'], [F(8), F(3)])
        self.assertEqual(data['covariance'], [[F(1), F(1)], [F(1), F(1)]])

    def test_empty_queue_and_zero_combination(self):
        mid = save_model(self.db, model())
        cohort = freeze_cohort(self.db, mid, [])
        empty = make_report(self.db, analyze(self.db, cohort, []), [])
        self.assertEqual(result(self.db, empty),
                         {'requests': [], 'statuses': [], 'estimates': [], 'covariance': []})
        analysis = analyze(self.db, cohort, [0])
        data = result(self.db, make_report(
            self.db, analysis, [request('level', (0, 1)), request('zero')]))
        self.assertEqual(data['statuses'], ['not_estimable', 'estimable'])
        self.assertEqual(data['estimates'], [None, F(0)])
        self.assertEqual(data['covariance'], [[None, None], [None, F(0)]])

    # ---- joint report: shared trajectory errors and frozen consumption ----

    def test_shared_innovations_full_joint_matrix_by_hand(self):
        # Independent unit level innovations u (t=2) and v (t=3). Hand
        # expansion: errors of x(2), x(3), x(3)-x(2), x(2)+x(3)-2x(1) are
        # [u, u+v, v, 2u+v], giving difference variance 1, cumulative 5.
        specification = model((0, 1, 2, 3),
                              [[[0, 0], [0, 0]], [[1, 0], [0, 0]], [[1, 0], [0, 0]]])
        rows = [reading('a', 0, 2), reading('b', 1, 5)]
        analysis = self._build(
            rows, [1, 2, 3], [], specification)[1]
        trajectory = read_artifact(self.db, analysis)['payload']['trajectory']
        self.assertEqual(trajectory['covariance'],
                         [[0, 0, 0], [0, 1, 1], [0, 1, 2]])
        report_id = make_report(self.db, analysis, [
            request('two', (2, 1)), request('three', (3, 1)),
            request('difference', (3, 1), (2, -1)),
            request('cumulative', (2, 1), (3, 1), (1, -2))])
        data = result(self.db, report_id)
        self.assertEqual(data['estimates'], [F(8), F(11), F(3), F(9)])
        self.assertEqual(data['covariance'],
                         [[1, 1, 0, 2], [1, 2, 1, 3], [0, 1, 1, 1], [2, 3, 1, 5]])

    def test_report_consumes_frozen_analysis_only(self):
        # A second report from the same fixed analysis must reproduce identical
        # numbers even after a correction creates a newer source head.
        specification = model((0, 1, 2), [[[0, 0], [0, 0]], [[0, 0], [0, 0]]])
        cohort, analysis, report_id = self._build(
            [reading('a', 0, 2), reading('b', 1, 5)], [0, 1, 2],
            [request('future', (2, 1))], specification)
        frozen = result(self.db, report_id)
        save_readings(self.db, [reading('b', 1, 6, rev=2)])
        again = make_report(self.db, analysis, [request('future', (2, 1))])
        self.assertEqual(result(self.db, again), frozen)
        self.assertEqual(result(self.db, again)['estimates'], [F(8)])

    def _build(self, rows, targets, requests, specification):
        model_id = save_model(self.db, specification)
        save_readings(self.db, rows)
        cohort_id = freeze_cohort(
            self.db, model_id, [(row['measurement_id'], row['rev']) for row in rows])
        analysis_id = analyze(self.db, cohort_id, targets)
        report_id = make_report(self.db, analysis_id, requests)
        return cohort_id, analysis_id, report_id


if __name__ == '__main__':
    unittest.main()
