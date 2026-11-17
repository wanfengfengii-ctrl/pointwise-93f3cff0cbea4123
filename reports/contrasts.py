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
    # Reports only consume the frozen analysis: its representative estimates,
    # retained unknown directions and complete joint covariance. They never
    # re-infer the trajectory.
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
                # Full bilinear form over the common trajectory errors; this
                # keeps the shared-innovation cross terms of change contrasts.
                row.append(sum((left[r] * trajectory.covariance[r][s] * right[s]
                                for r in range(len(left))
                                for s in range(len(right))), F(0)))
        covariance.append(tuple(row))
    return statuses, estimates, tuple(covariance)
