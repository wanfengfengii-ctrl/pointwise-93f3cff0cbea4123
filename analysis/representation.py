from dataclasses import dataclass
from fractions import Fraction
from analysis.algebra import psd_factor


@dataclass(frozen=True)
class JointTrajectory:
    targets: tuple
    estimates: tuple
    unknown_directions: tuple
    covariance: tuple
    latent_ids: tuple

    def to_payload(self):
        validate_joint_trajectory(self)
        return {'targets': list(self.targets), 'estimates': list(self.estimates),
                'unknown_directions': [list(v) for v in self.unknown_directions],
                'covariance': [list(row) for row in self.covariance],
                'latent_ids': list(self.latent_ids)}

    @classmethod
    def from_payload(cls, payload):
        if set(payload) != {'targets', 'estimates', 'unknown_directions',
                           'covariance', 'latent_ids'}:
            raise ValueError('joint trajectory fields')
        result = cls(tuple(payload['targets']), tuple(payload['estimates']),
                     tuple(tuple(v) for v in payload['unknown_directions']),
                     tuple(tuple(row) for row in payload['covariance']),
                     tuple(payload['latent_ids']))
        validate_joint_trajectory(result)
        return result


def validate_joint_trajectory(result):
    n = len(result.targets)
    if len(set(result.targets)) != n or len(result.estimates) != n:
        raise ValueError('joint target order/dimensions')
    if (len(result.covariance) != n or any(len(row) != n for row in result.covariance)
            or any(len(v) != n for v in result.unknown_directions)):
        raise ValueError('joint error dimensions')
    numbers = (list(result.targets) + list(result.estimates)
               + [x for row in result.covariance for x in row]
               + [x for v in result.unknown_directions for x in v])
    if any(not isinstance(x, Fraction) for x in numbers):
        raise ValueError('joint state requires Fraction values')
    if (len(set(result.latent_ids)) != len(result.latent_ids)
            or any(type(s) is not str for s in result.latent_ids)):
        raise ValueError('invalid common latent identities')
    psd_factor(result.covariance)
