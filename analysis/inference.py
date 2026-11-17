from fractions import Fraction as F
from analysis.algebra import dot
from analysis.constraints import reduce_exact_constraints
from analysis.representation import JointTrajectory, validate_joint_trajectory


def infer_joint_trajectory(design):
    """BLUE of the joint trajectory with its full error covariance.

    Initial level and slope are unknown fixed parameters without a finite
    prior. One exact KKT elimination gives the affine representative, the
    retained unknown (flat) directions, and the response of the solving map to
    each independent stochastic coordinate. Targets inherit the same common
    trajectory errors, so every cross-target covariance term is kept.
    """
    conditioned = reduce_exact_constraints(design)
    target_rows = design.target_matrix
    weights = design.weights

    estimates = tuple(dot(row, conditioned.representative) for row in target_rows)

    # Unknown directions expressed on the ordered target coordinates; a target
    # combination c is estimable exactly when c is orthogonal to all of them.
    raw_directions = [
        tuple(dot(row, basis) for row in target_rows) for basis in conditioned.null_basis
    ]
    unknown_directions = tuple(direction for direction in raw_directions
                               if any(direction))

    # Error covariance from the same solving map. Stationarity row k reads
    # (1/v_k) theta_k - (H'lambda)_k = f_k. Moving the physical latent error
    # z_k (variance v_k) to the forcing side gives f_k = (1/v_k) z_k, so the
    # target response to z_k is (1/v_k) * (g . profile_k). Independent
    # coordinates then contribute v_k times the outer product of those
    # responses, which simplifies to (g.profile_k)(g'.profile_k) / v_k.
    # Every cross term is retained for the joint change report.
    sensitivities = [
        [dot(row, profile) / weights[column]
         for profile, column in zip(conditioned.error_profiles,
                                    conditioned.random_columns)]
        for row in target_rows
    ]
    covariance = []
    for i, left in enumerate(sensitivities):
        line = []
        for j, right in enumerate(sensitivities):
            line.append(sum((left[k] * right[k] * weights[column]
                             for k, column in enumerate(conditioned.random_columns)), F(0)))
        covariance.append(tuple(line))

    result = JointTrajectory(design.targets, estimates, unknown_directions,
                             tuple(covariance), design.latent_ids)
    validate_joint_trajectory(result)
    return result
