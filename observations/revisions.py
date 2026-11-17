from dataclasses import dataclass
from fractions import Fraction


class RevisionConflict(ValueError):
    pass


@dataclass(frozen=True)
class MeasurementRevision:
    measurement_id: str
    rev: int
    time: Fraction
    value: Fraction | None
    variance: Fraction
    unit: str
    time_unit: str
    withdrawn: bool = False

    @property
    def identity(self):
        return self.measurement_id, self.rev

    def to_payload(self):
        return {name: getattr(self, name) for name in self.__dataclass_fields__}

    @classmethod
    def from_payload(cls, payload):
        from observations.validation import validate_reading
        return validate_reading(payload)


@dataclass(frozen=True)
class RevisionPlan:
    accepted: tuple
    ignored: tuple


def plan_revisions(incoming, existing, heads):
    unique = {}
    replayed = []
    for item in incoming:
        key = item.identity
        if key in unique:
            if unique[key] != item:
                raise RevisionConflict('conflicting revision within batch')
            replayed.append(key)
        unique[key] = item
    for key, item in unique.items():
        if key in existing and existing[key] != item:
            raise RevisionConflict('immutable revision conflict')
    accepted, ignored = [], list(replayed)
    for key, item in unique.items():
        if key in existing or item.rev <= heads.get(item.measurement_id, 0):
            ignored.append(key)
        else:
            accepted.append(item)
    return RevisionPlan(tuple(accepted), tuple(ignored))
