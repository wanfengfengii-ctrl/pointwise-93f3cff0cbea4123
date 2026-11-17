from dataclasses import dataclass
from fractions import Fraction as F
from analysis.algebra import psd_factor


@dataclass(frozen=True)
class TrajectoryDesign:
    targets: tuple
    observation_matrix: tuple
    observations: tuple
    target_matrix: tuple
    weights: tuple
    latent_ids: tuple


def transition_matrix(delta):
    if not isinstance(delta, F):
        delta = F(delta)
    return ((F(1), delta), (F(0), F(1)))


def build_trajectory_design(cohort, targets):
    model = cohort.model
    if not isinstance(targets, (list, tuple)):
        raise ValueError('targets must be an ordered sequence')
    parsed = []
    for t in targets:
        if isinstance(t, bool) or not isinstance(t, (int, str, F)):
            raise ValueError('target requires exact rational time')
        try:
            parsed.append(F(t))
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError('invalid target rational') from exc
    targets = tuple(parsed)
    if len(set(targets)) != len(targets):
        raise ValueError('duplicate analysis target')
    earliest = min((r.time for r in cohort.members), default=model.knots[0])
    if any(t < earliest or t < model.knots[0] or t > model.knots[-1] for t in targets):
        raise ValueError('target outside observation/model support')
    weights = [F(0), F(0)]
    identities = ['initial:level', 'initial:slope']
    events = []
    for interval, q in enumerate(model.innovations):
        vectors, variances = psd_factor(q)
        for axis, (vector, variance) in enumerate(zip(vectors, variances)):
            events.append((model.knots[interval + 1], vector, len(weights)))
            weights.append(variance)
            identities.append('process:%d:%d' % (interval, axis))
    observed = [r for r in cohort.members if r.value is not None]
    measurement_columns = {}
    for item in observed:
        if item.variance:
            measurement_columns[item.identity] = len(weights)
            weights.append(item.variance)
            identities.append('measurement:%s:%d' % item.identity)
    n = len(weights)

    def level(t):
        row = [F(0)] * n
        row[0], row[1] = transition_matrix(t - model.knots[0])[0]
        for event_time, vector, column in events:
            if event_time <= t:
                row[column] = vector[0] + (t - event_time) * vector[1]
        return row

    h, y = [], []
    for item in observed:
        row = level(item.time)
        column = measurement_columns.get(item.identity)
        if column is not None:
            row[column] = F(1)
        h.append(tuple(row))
        y.append(item.value)
    return TrajectoryDesign(targets, tuple(h), tuple(y),
                            tuple(tuple(level(t)) for t in targets),
                            tuple(weights), tuple(identities))
