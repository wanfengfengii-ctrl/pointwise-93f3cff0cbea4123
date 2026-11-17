from fractions import Fraction as F
from analysis.algebra import dot
from analysis.constraints import reduce_exact_constraints
from analysis.representation import JointTrajectory, validate_joint_trajectory


def infer_joint_trajectory(design):
    conditioned = reduce_exact_constraints(design)
    rows = design.target_matrix
    estimates = tuple(dot(row, conditioned.mean) for row in rows)
    variances = tuple(
        sum((row[j] * conditioned.covariance[j][k] * row[k]
             for j in range(conditioned.latent_count)
             for k in range(conditioned.latent_count)), F(0))
        for row in rows)
    covariance = tuple(tuple(variances[i] if i == j else F(0)
                             for j in range(len(rows)))
                       for i in range(len(rows)))
    result = JointTrajectory(design.targets, estimates, (), covariance,
                             design.latent_ids)
    validate_joint_trajectory(result)
    return result
