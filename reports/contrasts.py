from fractions import Fraction as F
from analysis.algebra import dot
from analysis.identifiability import classify_contrasts


def compile_contrasts(trajectory, requests):
    rows = []
    for request in requests:
        terms = dict(request.terms)
        if any(time not in trajectory.targets for time in terms):
            raise ValueError('contrast target not in trajectory')
        rows.append(tuple(terms.get(t, F(0)) for t in trajectory.targets))
    return tuple(rows)


def evaluate_contrasts(trajectory, contrasts):
    statuses = classify_contrasts(trajectory, contrasts)
    estimates = tuple(dot(row, trajectory.estimates) if status == 'estimable' else None
                      for row, status in zip(contrasts, statuses))
    covariance = []
    for i, left in enumerate(contrasts):
        row = []
        for j, right in enumerate(contrasts):
            if statuses[i] != 'estimable' or statuses[j] != 'estimable':
                row.append(None)
            else:
                row.append(sum((left[r] * trajectory.covariance[r][r] * right[r]
                                for r in range(len(left))), F(0)))
        covariance.append(tuple(row))
    return statuses, estimates, tuple(covariance)
