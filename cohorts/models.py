from dataclasses import dataclass
from fractions import Fraction
from analysis.algebra import psd_factor


class InvalidModel(ValueError):
    pass


def _rational(value):
    if isinstance(value, bool) or not isinstance(value, (int, str, Fraction)):
        raise InvalidModel('model requires exact rational values')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise InvalidModel('invalid model rational') from exc


@dataclass(frozen=True)
class ModelVersion:
    name: str
    rev: int
    unit: str
    time_unit: str
    knots: tuple
    innovations: tuple

    def to_payload(self):
        return {'name': self.name, 'rev': self.rev, 'unit': self.unit,
                'time_unit': self.time_unit, 'knots': list(self.knots),
                'innovations': [[list(row) for row in q] for q in self.innovations]}

    @classmethod
    def from_payload(cls, payload):
        return validate_model(payload)


def validate_model(raw):
    fields = {'name', 'rev', 'unit', 'time_unit', 'knots', 'innovations'}
    if not isinstance(raw, dict) or set(raw) != fields:
        raise InvalidModel('model fields')
    if any(not isinstance(raw[k], str) or not raw[k].strip()
           for k in ('name', 'unit', 'time_unit')):
        raise InvalidModel('model identity and units')
    if type(raw['rev']) is not int or raw['rev'] < 1:
        raise InvalidModel('model revision')
    if not isinstance(raw['knots'], (list, tuple)) or not raw['knots']:
        raise InvalidModel('nonempty time support required')
    knots = tuple(_rational(t) for t in raw['knots'])
    if any(a >= b for a, b in zip(knots, knots[1:])):
        raise InvalidModel('knots must be strictly increasing')
    if not isinstance(raw['innovations'], (list, tuple)):
        raise InvalidModel('innovations must be a sequence')
    if len(raw['innovations']) != len(knots) - 1:
        raise InvalidModel('one innovation covariance per interval')
    matrices = []
    for q in raw['innovations']:
        if (not isinstance(q, (list, tuple)) or len(q) != 2
                or any(not isinstance(row, (list, tuple)) or len(row) != 2 for row in q)):
            raise InvalidModel('innovation covariance must be two dimensional')
        q = tuple(tuple(_rational(x) for x in row) for row in q)
        try:
            psd_factor(q)
        except ValueError as exc:
            raise InvalidModel(str(exc)) from exc
        matrices.append(q)
    return ModelVersion(raw['name'], raw['rev'], raw['unit'], raw['time_unit'],
                        knots, tuple(matrices))
