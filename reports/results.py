from dataclasses import dataclass
from fractions import Fraction
from analysis.algebra import psd_factor


@dataclass(frozen=True)
class JointReport:
    requests: tuple
    statuses: tuple
    estimates: tuple
    covariance: tuple

    def to_payload(self):
        validate_report_result(self)
        return {'requests': [r.to_payload() for r in self.requests],
                'statuses': list(self.statuses), 'estimates': list(self.estimates),
                'covariance': [list(row) for row in self.covariance]}

    @classmethod
    def from_payload(cls, payload):
        from reports.requests import RequestSpec
        if set(payload) != {'requests', 'statuses', 'estimates', 'covariance'}:
            raise ValueError('report fields')
        requests = tuple(RequestSpec(r['label'], tuple(tuple(p) for p in r['terms']))
                         for r in payload['requests'])
        result = cls(requests, tuple(payload['statuses']), tuple(payload['estimates']),
                     tuple(tuple(row) for row in payload['covariance']))
        validate_report_result(result)
        return result


def validate_report_result(result):
    n = len(result.requests)
    if (n > 8 or len(result.statuses) != n or len(result.estimates) != n
            or len(result.covariance) != n or any(len(row) != n for row in result.covariance)):
        raise ValueError('report dimensions')
    for request in result.requests:
        if (not isinstance(request.label, str) or not request.label.strip()
                or len({t for t, _ in request.terms}) != len(request.terms)
                or any(not isinstance(x, Fraction) for p in request.terms for x in p)):
            raise ValueError('invalid normalized report request')
    for i, status in enumerate(result.statuses):
        if status not in ('estimable', 'not_estimable'):
            raise ValueError('invalid report status')
        value = result.estimates[i]
        if (status == 'not_estimable' and value is not None
                or status == 'estimable' and not isinstance(value, Fraction)):
            raise ValueError('estimate/status mismatch')
        for j in range(n):
            cell = result.covariance[i][j]
            masked = status == 'not_estimable' or result.statuses[j] == 'not_estimable'
            if masked and cell is not None:
                raise ValueError('unidentified covariance row/column must be None')
            if not masked and not isinstance(cell, Fraction):
                raise ValueError('finite covariance requires Fraction')
            if cell != result.covariance[j][i]:
                raise ValueError('asymmetric report covariance')
    finite = [i for i, s in enumerate(result.statuses) if s == 'estimable']
    psd_factor([[result.covariance[i][j] for j in finite] for i in finite])
