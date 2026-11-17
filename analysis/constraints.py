from dataclasses import dataclass
from fractions import Fraction as F
from analysis.algebra import rref


class ExactInconsistency(ValueError):
    pass


@dataclass(frozen=True)
class ConstraintReduction:
    # Representative minimizer theta* in latent coordinates (an affine BLUE
    # representative; free fixed parameters are taken at zero).
    representative: tuple
    # Flat directions of the constrained minimum, projected back to latent
    # theta coordinates. Entries on positive-precision coordinates are zero.
    null_basis: tuple
    # For every positive-precision latent column k, the theta-part of the
    # response of the KKT solving map to a unit stationarity forcing at k.
    error_profiles: tuple
    random_columns: tuple
    latent_count: int
    observation_count: int


def reduce_exact_constraints(design):
    """Exact constrained minimum of the stochastic precision sum.

    Latent coordinates theta=(beta, stochastic coordinates) have independent
    variances in design.weights; the fixed initial level/slope and exact
    measurement coordinates have zero variance, i.e. zero precision and no
    finite prior. With precision P=diag(1/variance), the observations satisfy
    H theta = y exactly. Minimizing 1/2 theta' P theta under those constraints
    is solved once, in exact rationals, via the KKT system

        [P  -H'] [theta]   [r]
        [H    0] [lambda] = [y]

    using one joint Gauss-Jordan elimination with several right-hand sides:
    the observation vector y plus one unit stationarity forcing per stochastic
    coordinate, which yields the response of the same solving map used for the
    BLUE error covariance. Inconsistent exact constraints raise ExactInconsistency.
    """
    h = [list(row) for row in design.observation_matrix]
    m = len(h)
    n = len(design.weights)
    variances = design.weights
    random_columns = tuple(k for k, variance in enumerate(variances) if variance > 0)
    precision = [F(1) / variance if variance > 0 else F(0)
                 for variance in variances]
    width = n + m

    # KKT rows: stationarity P theta - H' lambda = r for every latent column
    # (fixed beta and exact-reading columns carry a zero precision row),
    # followed by the constraint rows H theta = y. The -H' lambda coupling is
    # present on stochastic columns too, since measurement and process columns
    # occur in H.
    coefficient = [[F(0)] * width for _ in range(width)]
    for k, value in enumerate(precision):
        if value:
            coefficient[k][k] = value
    for i, row in enumerate(h):
        for k, value in enumerate(row):
            if value:
                coefficient[k][n + i] = -value
        coefficient[n + i][:n] = list(row)

    rhs_columns = 1 + len(random_columns)
    rhs = [[F(0)] * rhs_columns for _ in range(width)]
    for i, value in enumerate(design.observations):
        rhs[n + i][0] = value
    for j, k in enumerate(random_columns):
        rhs[k][j + 1] = F(1)

    rows, pivots = rref([coefficient[i] + rhs[i] for i in range(width)], columns=width)
    for row in rows:
        if not any(row[:width]) and row[width]:
            raise ExactInconsistency('conflicting exact constraints')

    pivot_columns = set(pivots)
    null_basis = []
    for free in range(width):
        if free in pivot_columns:
            continue
        vector = [F(0)] * width
        vector[free] = F(1)
        for i, pivot in enumerate(pivots):
            vector[pivot] = -rows[i][free]
        theta_part = vector[:n]
        if any(theta_part):
            null_basis.append(tuple(theta_part))
    # Flat directions cannot move stochastic coordinates: v'Pv = 0 with
    # positive precisions forces every stochastic entry to vanish exactly.
    for vector in null_basis:
        if any(vector[k] for k in random_columns):
            raise RuntimeError('flat direction leaked into stochastic coordinates')

    representative = [F(0)] * width
    for i, pivot in enumerate(pivots):
        representative[pivot] = rows[i][width]

    error_profiles = []
    for j in range(len(random_columns)):
        response = [F(0)] * width
        for i, pivot in enumerate(pivots):
            response[pivot] = rows[i][width + 1 + j]
        error_profiles.append(tuple(response[:n]))

    return ConstraintReduction(tuple(representative[:n]), tuple(null_basis),
                               tuple(error_profiles), random_columns, n, m)
