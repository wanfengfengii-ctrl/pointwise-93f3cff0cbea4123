from fractions import Fraction
from observations.revisions import MeasurementRevision


class InvalidReading(ValueError):
    pass


def parse_fraction(value):
    try:
        if isinstance(value, bool) or not isinstance(value, (int, str, Fraction)):
            raise ValueError('use integer, fraction string or Fraction')
        return Fraction(value)
    except (ValueError, TypeError, ZeroDivisionError) as exc:
        raise InvalidReading('invalid exact rational') from exc


def validate_reading(raw):
    fields = set(MeasurementRevision.__dataclass_fields__)
    if not isinstance(raw, dict) or set(raw) - fields:
        raise InvalidReading('unknown reading fields')
    required = fields - {'withdrawn'}
    if not required <= set(raw):
        raise InvalidReading('missing reading fields')
    for key in ('measurement_id', 'unit', 'time_unit'):
        if not isinstance(raw[key], str) or not raw[key].strip():
            raise InvalidReading('identity and units must be nonempty strings')
    rev = raw['rev']
    if isinstance(rev, bool) or not isinstance(rev, int) or rev < 1:
        raise InvalidReading('revision must be a positive integer')
    withdrawn = raw.get('withdrawn', False)
    if type(withdrawn) is not bool:
        raise InvalidReading('withdrawn must be boolean')
    variance = parse_fraction(raw['variance'])
    if variance < 0:
        raise InvalidReading('negative measurement variance')
    return MeasurementRevision(
        raw['measurement_id'], rev, parse_fraction(raw['time']),
        None if raw['value'] is None else parse_fraction(raw['value']),
        variance, raw['unit'], raw['time_unit'], withdrawn)


def validate_reading_batch(batch):
    if not isinstance(batch, (list, tuple)):
        raise InvalidReading('batch must be a sequence')
    return tuple(validate_reading(raw) for raw in batch)
