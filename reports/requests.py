from dataclasses import dataclass
from fractions import Fraction


class InvalidRequest(ValueError):
    pass


def _fraction(value):
    if isinstance(value, bool) or not isinstance(value, (int, str, Fraction)):
        raise InvalidRequest('request requires exact rational values')
    try:
        return Fraction(value)
    except (ValueError, ZeroDivisionError) as exc:
        raise InvalidRequest('invalid request rational') from exc


@dataclass(frozen=True)
class RequestSpec:
    label: str
    terms: tuple

    def to_payload(self):
        return {'label': self.label, 'terms': [list(pair) for pair in self.terms]}


def normalize_requests(raw, targets):
    if not isinstance(raw, (list, tuple)) or len(raw) > 8:
        raise InvalidRequest('requests must be an ordered sequence of at most eight items')
    result = []
    for request in raw:
        if (not isinstance(request, dict) or set(request) != {'label', 'terms'}
                or not isinstance(request['label'], str) or not request['label'].strip()
                or not isinstance(request['terms'], (list, tuple))):
            raise InvalidRequest('invalid request fields')
        terms = {}
        for pair in request['terms']:
            if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                raise InvalidRequest('terms must be time/coefficient pairs')
            time, coefficient = (_fraction(x) for x in pair)
            if time not in targets:
                raise InvalidRequest('target not bound by specified analysis')
            terms[time] = terms.get(time, Fraction(0)) + coefficient
        result.append(RequestSpec(request['label'],
                                  tuple((t, terms[t]) for t in targets if terms.get(t))))
    return tuple(result)
