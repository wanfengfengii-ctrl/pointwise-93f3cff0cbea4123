from fractions import Fraction as F
from reports.service import make_report
from reports.requests import InvalidRequest
from reports.results import JointReport
from tests.test_workflow import (WorkflowCase, reading, model, request, pipeline,
                                 result, counts, scenario)


class TestReports(WorkflowCase):
    def test_partial_estimability(self):
        _, _, report = pipeline(self.db, [reading('a', 0, 2)], [0, 1],
                                [request('now', (0, 1)), request('future', (1, 1)),
                                 request('change', (1, 1), (0, -1))])
        data = result(self.db, report)
        self.assertEqual(data['statuses'], ['estimable', 'not_estimable', 'not_estimable'])
        self.assertEqual(data['estimates'], [F(2), None, None])
        self.assertEqual(data['covariance'], [[F(0), None, None],
                                              [None, None, None], [None, None, None]])

    def test_mask_order_and_cancellation(self):
        _, analysis, _ = pipeline(self.db, [reading('a', 0, 2)], [0, 1, 2], [])
        report = make_report(self.db, analysis,
                             [request('future', (1, 1)), request('now', (0, 1)),
                              request('zero', (1, 1), (1, -1)),
                              request('curvature', (2, 1), (1, -2), (0, 1))])
        data = result(self.db, report)
        self.assertEqual(data['statuses'], ['not_estimable', 'estimable', 'estimable', 'estimable'])
        self.assertEqual(data['estimates'], [None, F(2), F(0), F(0)])
        self.assertEqual(data['covariance'],
                         [[None, None, None, None], [None, F(0), F(0), F(0)],
                          [None, F(0), F(0), F(0)], [None, F(0), F(0), F(0)]])
        JointReport.from_payload(data)

    def future(self):
        specification = model((0, 1, 2, 3),
                              [[[0, 0], [0, 0]], [[1, 0], [0, 0]], [[1, 0], [0, 0]]])
        return pipeline(self.db, [reading('a', 0, 2), reading('b', 1, 5)], [0, 1, 2, 3],
                        [request('two', (2, 1)), request('three', (3, 1)),
                         request('difference', (3, 1), (2, -1)),
                         request('cumulative', (2, 1), (3, 1), (1, -2))], specification)

    def test_shared_future_innovations(self):
        _, analysis, report = self.future()
        data = result(self.db, report)
        expected = [[1, 1, 0, 2], [1, 2, 1, 3], [0, 1, 1, 1], [2, 3, 1, 5]]
        self.assertEqual(data['estimates'], [F(8), F(11), F(3), F(9)])
        self.assertEqual(data['covariance'], expected)
        widths = {'difference_variance': data['covariance'][2][2],
                  'cumulative_variance': data['covariance'][3][3]}
        self.assertEqual(widths, {'difference_variance': 1, 'cumulative_variance': 5})
        scenario('v6.joint_contrasts', {'initial_levels': [2, 5], 'future_level_innovation_variances': [1, 1]},
                 {'estimates': [8, 11, 3, 9], 'covariance': expected},
                 {'estimates': data['estimates'], 'covariance': data['covariance']},
                 {'difference_variance': 1, 'cumulative_variance': 5}, widths,
                 ['analysis/dynamics.py', 'analysis/inference.py', 'analysis/representation.py',
                  'reports/contrasts.py', 'reports/service.py'],
                 'Independent unit innovations u,v give errors [u,u+v,v,2u+v].')
        for index, specification in enumerate(data['requests']):
            single = make_report(self.db, analysis, [specification])
            self.assertEqual(result(self.db, single)['estimates'], [data['estimates'][index]])
            self.assertEqual(result(self.db, single)['covariance'], [[expected[index][index]]])

    def test_permutation(self):
        _, analysis, identity = self.future()
        data = result(self.db, identity)
        order = [3, 0, 2, 1]
        identity = make_report(self.db, analysis, [data['requests'][i] for i in order])
        permuted = result(self.db, identity)
        self.assertEqual(permuted['estimates'], [data['estimates'][i] for i in order])
        self.assertEqual(permuted['covariance'],
                         [[data['covariance'][i][j] for j in order] for i in order])

    def test_request_rejection(self):
        _, analysis, _ = self.straight()
        before = counts(self.db)
        bad = [[request('x', (2, 1))] * 9, [request('unknown', (3, 1))],
               [request('bad', (2, True))], [request('bad', (2, 0.5))],
               [{'label': 'x', 'terms': [[2]]}]]
        for requests in bad:
            with self.assertRaises(InvalidRequest):
                make_report(self.db, analysis, requests)
            self.assertEqual(counts(self.db), before)
        empty = make_report(self.db, analysis, [])
        self.assertEqual(result(self.db, empty)['estimates'], [])
        self.assertEqual(result(self.db, empty)['covariance'], [])

    def test_positive_noise_handcheck(self):
        # At t=0 two independent unit-noise readings average to 3 with variance 1/2.
        _, _, identity = pipeline(self.db, [reading('a', 0, 2, 1), reading('b', 0, 4, 1)], [0, 1],
                                  [request('now', (0, 1)), request('future', (1, 1))])
        data = result(self.db, identity)
        self.assertEqual(data['estimates'], [F(3), None])
        self.assertEqual(data['covariance'], [[F(1, 2), None], [None, None]])
