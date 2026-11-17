from dataclasses import dataclass
from cohorts.models import ModelVersion
from cohorts.selection import InvalidSelection
from observations.revisions import MeasurementRevision


@dataclass(frozen=True)
class FrozenCohort:
    model_id: str
    model: ModelVersion
    members: tuple

    def to_payload(self):
        return {'model_id': self.model_id, 'model': self.model.to_payload(),
                'members': [item.to_payload() for item in self.members]}

    @classmethod
    def from_payload(cls, payload):
        return bind_cohort(payload['model_id'], ModelVersion.from_payload(payload['model']),
                           tuple(MeasurementRevision.from_payload(r)
                                 for r in payload['members']))


def bind_cohort(model_id, model, members):
    seen = set()
    for item in members:
        if item.measurement_id in seen or item.withdrawn:
            raise InvalidSelection('duplicate or withdrawn cohort member')
        seen.add(item.measurement_id)
        if item.unit != model.unit or item.time_unit != model.time_unit:
            raise InvalidSelection('measurement and model units differ')
        if not model.knots[0] <= item.time <= model.knots[-1]:
            raise InvalidSelection('measurement outside model coverage')
    if len({r.time for r in members}) > 24:
        raise InvalidSelection('at most 24 observation times')
    return FrozenCohort(model_id, model, tuple(members))
