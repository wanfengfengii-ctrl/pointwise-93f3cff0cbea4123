from dataclasses import dataclass
from fractions import Fraction as F
from analysis.algebra import solve_affine, dot


class ExactInconsistency(ValueError):
    pass


@dataclass(frozen=True)
class ConstraintReduction:
    mean: tuple
    covariance: tuple
    latent_count: int
    observation_count: int


def _projected_solve(matrix, rhs):
    n = len(matrix)
    normal = [[sum((matrix[k][i] * matrix[k][j] for k in range(n)), F(0))
               for j in range(n)] for i in range(n)]
    target = [sum((matrix[k][i] * rhs[k] for k in range(n)), F(0))
              for i in range(n)]
    return solve_affine(normal, target, ncols=n)[0]


def reduce_exact_constraints(design):
    h = design.observation_matrix
    n, m = len(design.weights), len(h)
    prior = tuple(value if value else F(1) for value in design.weights)
    observation_covariance = [
        [sum((h[i][k] * prior[k] * h[j][k] for k in range(n)), F(0))
         for j in range(m)] for i in range(m)]
    coefficients = _projected_solve(observation_covariance, design.observations)
    mean = tuple(prior[k] * sum((h[i][k] * coefficients[i]
                                for i in range(m)), F(0)) for k in range(n))
    columns = []
    for k in range(n):
        columns.append(_projected_solve(
            observation_covariance, [h[i][k] * prior[k] for i in range(m)]))
    covariance = []
    for j in range(n):
        row = []
        cross = [prior[j] * h[i][j] for i in range(m)]
        for k in range(n):
            row.append((prior[j] if j == k else F(0)) - dot(cross, columns[k]))
        covariance.append(tuple(row))
    return ConstraintReduction(mean, tuple(covariance), n, m)
