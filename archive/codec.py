import hashlib
import json
from fractions import Fraction


def _pack(value):
    if isinstance(value, Fraction):
        return {'$fraction': [value.numerator, value.denominator]}
    if value is None or type(value) in (str, int, bool):
        return value
    if isinstance(value, (list, tuple)):
        return [_pack(v) for v in value]
    if isinstance(value, dict) and all(type(k) is str for k in value):
        if '$fraction' in value:
            raise ValueError('reserved encoding key')
        return {k: _pack(v) for k, v in value.items()}
    raise ValueError('unsupported payload type')


def _unpack(value):
    if isinstance(value, dict):
        if '$fraction' in value:
            if set(value) != {'$fraction'}:
                raise ValueError('invalid rational tag')
            pair = value['$fraction']
            if (not isinstance(pair, list) or len(pair) != 2
                    or any(type(v) is not int for v in pair)
                    or pair[1] <= 0):
                raise ValueError('invalid rational encoding')
            f = Fraction(*pair)
            if [f.numerator, f.denominator] != pair:
                raise ValueError('noncanonical rational')
            return f
        return {k: _unpack(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_unpack(v) for v in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise ValueError('unsupported JSON value')


def encode_payload(payload):
    return json.dumps(_pack(payload), ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False)


def decode_payload(text):
    value = _unpack(json.loads(text))
    if encode_payload(value) != text:
        raise ValueError('noncanonical payload')
    return value


def payload_digest(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()
