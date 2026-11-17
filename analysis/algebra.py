from fractions import Fraction as F


def transpose(a):
    return [list(row) for row in zip(*a)] if a else []


def dot(a, b):
    return sum((x * y for x, y in zip(a, b)), F(0))


def matmul(a, b):
    if not a:
        return []
    if not b:
        return [[] for _ in a]
    if any(len(row) != len(b) for row in a):
        raise ValueError('matrix dimensions')
    return [[dot(row, col) for col in transpose(b)] for row in a]


def rref(matrix, columns=None):
    a = [[F(x) for x in row] for row in matrix]
    width = len(a[0]) if a else (columns or 0)
    if any(len(row) != width for row in a):
        raise ValueError('ragged matrix')
    limit = width if columns is None else columns
    pivots = []
    # Eliminate coefficient columns first; augmented right-hand-side columns
    # are reduced afterwards so every RHS is fully carried to pivot rows.
    for c in range(width):
        p = next((i for i in range(len(pivots), len(a)) if a[i][c]), None)
        if p is None:
            continue
        r = len(pivots)
        a[r], a[p] = a[p], a[r]
        scale = a[r][c]
        a[r] = [v / scale for v in a[r]]
        for i in range(len(a)):
            if i != r and a[i][c]:
                scale = a[i][c]
                a[i] = [x - scale * y for x, y in zip(a[i], a[r])]
        if c < limit:
            pivots.append(c)
        if len(pivots) == len(a):
            break
    return a, pivots


def solve_affine(a, b, ncols=None):
    n = len(a[0]) if a else (ncols or 0)
    if len(a) != len(b):
        raise ValueError('right hand side dimensions')
    rows, pivots = rref([list(row) + [v] for row, v in zip(a, b)], n)
    if any(not any(row[:n]) and row[n] for row in rows):
        raise ValueError('inconsistent linear system')
    x = [F(0)] * n
    for i, p in enumerate(pivots):
        x[p] = rows[i][n]
    basis = []
    for j in range(n):
        if j not in pivots:
            v = [F(0)] * n
            v[j] = F(1)
            for i, p in enumerate(pivots):
                v[p] = -rows[i][j]
            basis.append(v)
    return x, basis


def nullspace(a, ncols=None):
    return solve_affine(a, [F(0)] * len(a), ncols)[1]


def psd_factor(matrix):
    a = [[F(x) for x in row] for row in matrix]
    n = len(a)
    if any(len(row) != n for row in a):
        raise ValueError('covariance must be square')
    if any(a[i][j] != a[j][i] for i in range(n) for j in range(n)):
        raise ValueError('covariance must be symmetric')
    vectors, weights = [], []
    for i in range(n):
        d = a[i][i]
        if d < 0:
            raise ValueError('covariance is not positive semidefinite')
        if not d:
            if any(a[i][j] for j in range(i + 1, n)):
                raise ValueError('zero pivot with nonzero covariance')
            continue
        v = [F(0)] * n
        for j in range(i, n):
            v[j] = a[j][i] / d
        vectors.append(v)
        weights.append(d)
        for j in range(i + 1, n):
            for k in range(i + 1, n):
                a[j][k] -= d * v[j] * v[k]
    return vectors, weights
