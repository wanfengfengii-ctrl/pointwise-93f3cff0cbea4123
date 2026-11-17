from fractions import Fraction as F
from analysis.service import analyze
from analysis.constraints import ExactInconsistency
from analysis.representation import JointTrajectory
from cohorts.service import save_model, freeze_cohort
from observations.service import save_readings
from reports.service import make_report
from archive.reading import read_artifact
from tests.test_workflow import WorkflowCase, reading, model, request, pipeline, result, counts


def independent_solve(matrix, rhs):
    # Separate dense Gauss-Jordan oracle; no production algebra or inference.
    rows = [[F(x) for x in row] + [F(y)] for row, y in zip(matrix, rhs)]
    n = len(rows)
    for j in range(n):
        pivot = next(i for i in range(j, n) if rows[i][j])
        rows[j], rows[pivot] = rows[pivot], rows[j]
        divisor = rows[j][j]
        rows[j] = [x / divisor for x in rows[j]]
        for i in range(n):
            if i != j:
                multiplier = rows[i][j]
                rows[i] = [x - multiplier * y for x, y in zip(rows[i], rows[j])]
    return [row[-1] for row in rows]


def direct_blue(rows, targets, specification):
    rows = [r for r in rows if r['value'] is not None]
    times = [F(r['time']) for r in rows]
    origin = F(specification['knots'][0])

    def process_cov(t, s):
        answer = F(0)
        for end, q in zip(specification['knots'][1:], specification['innovations']):
            end = F(end)
            if end <= min(t, s):
                left, right = [F(1), t - end], [F(1), s - end]
                answer += sum(left[i] * F(q[i][j]) * right[j]
                              for i in range(2) for j in range(2))
        return answer

    size = len(rows)
    v = [[process_cov(t, s) + (F(rows[i]['variance']) if i == j else 0)
          for j, s in enumerate(times)] for i, t in enumerate(times)]
    system = [v[i] + [F(1), times[i] - origin] for i in range(size)]
    system += [[F(1)] * size + [F(0), F(0)],
               [t - origin for t in times] + [F(0), F(0)]]
    weights, means = [], []
    for t in targets:
        w = independent_solve(system, [process_cov(t, s) for s in times] + [1, t - origin])[:size]
        weights.append(w)
        means.append(sum(wi * F(r['value']) for wi, r in zip(w, rows)))
    cov = []
    for i, t in enumerate(targets):
        cov.append([])
        for j, s in enumerate(targets):
            value = process_cov(t, s)
            value -= sum(weights[i][k] * process_cov(times[k], s) for k in range(size))
            value -= sum(weights[j][k] * process_cov(t, times[k]) for k in range(size))
            value += sum(weights[i][k] * v[k][l] * weights[j][l]
                         for k in range(size) for l in range(size))
            cov[-1].append(value)
    return means, cov


class TestAnalysis(WorkflowCase):
    def test_exact_linear_track(self):
        _, _, identity = self.straight()
        data = result(self.db, identity)
        self.assertEqual(data['estimates'], [F(8)])
        self.assertEqual(data['covariance'], [[F(0)]])

    def test_irregular_time(self):
        rows = [reading('a', 0, 2), reading('b', '3/2', '13/2')]
        _, _, identity = pipeline(self.db, rows, ['5/2'],
                                  [request('future', ('5/2', 1))],
                                  model((0, '3/2', '5/2')))
        self.assertEqual(result(self.db, identity)['estimates'], [F(19, 2)])
        self.assertEqual(result(self.db, identity)['covariance'], [[F(0)]])

    def test_conflicting_exact_observations(self):
        mid = save_model(self.db, model())
        save_readings(self.db, [reading('a', 1, 5), reading('b', 1, 6)])
        cohort = freeze_cohort(self.db, mid, [('a', 1), ('b', 1)])
        before = counts(self.db)
        with self.assertRaises(ExactInconsistency):
            analyze(self.db, cohort, [1, 2])
        self.assertEqual(counts(self.db), before)

    def test_independent_batch_oracle(self):
        specification = model((0, 1, 2, 3),
                              [[[1, '1/2'], ['1/2', 1]],
                               [[0, 0], [0, 0]], [[1, 0], [0, 0]]])
        rows = [reading('a', 0, 2, 1), reading('b', '3/2', 7, 2),
                reading('c', '3/2', 6, 3), reading('d', 2, 9, 1),
                reading('missing', '1/2', None)]
        targets = [F(0), F(3, 2), F(5, 2), F(3)]
        expected_mean, expected_cov = direct_blue(rows, targets, specification)
        _, analysis, report = pipeline(self.db, rows, targets,
                                      [request(str(t), (t, 1)) for t in targets], specification)
        data = result(self.db, report)
        self.assertEqual(data['estimates'], expected_mean)
        self.assertEqual(data['covariance'], expected_cov)
        trajectory = JointTrajectory.from_payload(read_artifact(self.db, analysis)['payload']['trajectory'])
        self.assertFalse(trajectory.unknown_directions)
        reversed_report = make_report(self.db, analysis,
                                      [request(str(t), (t, 1)) for t in reversed(targets)])
        reverse = result(self.db, reversed_report)
        self.assertEqual(reverse['estimates'], expected_mean[::-1])
        self.assertEqual(reverse['covariance'], [r[::-1] for r in expected_cov[::-1]])

    def test_singular_innovations(self):
        specification = model((0, 1, 2, 3),
                              [[[0, 0], [0, 0]], [[1, 1], [1, 1]], [[0, 0], [0, 0]]])
        _, _, identity = pipeline(self.db, [reading('a', 0, 2), reading('b', 1, 5)], [2, 3],
                                  [request('two', (2, 1)), request('three', (3, 1))], specification)
        data = result(self.db, identity)
        self.assertEqual(data['estimates'], [F(8), F(11)])
        self.assertEqual(data['covariance'], [[F(1), F(2)], [F(2), F(4)]])

    def test_target_validation_and_empty_analysis(self):
        mid = save_model(self.db, model())
        cohort = freeze_cohort(self.db, mid, [])
        before = counts(self.db)
        for targets in ([True], [4], [1, 1], [0.5], ['1/0'], ['bad']):
            with self.assertRaises(ValueError):
                analyze(self.db, cohort, targets)
            self.assertEqual(counts(self.db), before)
        analysis = analyze(self.db, cohort, [])
        report = make_report(self.db, analysis, [request('zero')])
        self.assertEqual(result(self.db, report)['estimates'], [F(0)])
