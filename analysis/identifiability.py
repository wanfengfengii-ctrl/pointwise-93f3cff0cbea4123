from analysis.algebra import dot


def contrast_is_estimable(trajectory, coefficients):
    if len(coefficients) != len(trajectory.targets):
        raise ValueError('contrast dimensions')
    return all(dot(coefficients, direction) == 0
               for direction in trajectory.unknown_directions)


def classify_contrasts(trajectory, contrasts):
    return tuple('estimable' if contrast_is_estimable(trajectory, row)
                 else 'not_estimable' for row in contrasts)
