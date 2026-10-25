"""Advisory metadata type comparisons, never casts or compatibility proofs."""
import re

_FAMILIES = {
    'numeric': {'tinyint', 'smallint', 'int', 'integer', 'bigint', 'int8', 'int16', 'int32', 'int64', 'uint8', 'uint16', 'uint32', 'uint64', 'float', 'float32', 'float64', 'double', 'real', 'decimal', 'numeric', 'number'},
    'text': {'string', 'text', 'varchar', 'char', 'character', 'nvarchar', 'nchar'},
    'boolean': {'bool', 'boolean'},
    'date': {'date'},
    'time': {'time'},
    'timestamp': {'timestamp', 'datetime', 'timestamp_ntz', 'timestamp_ltz', 'timestamp_tz'},
    'binary': {'binary', 'varbinary', 'bytes'},
}


def _scalar(value):
    if not isinstance(value, str):
        return None, None
    normalized = re.sub(r'\s+', '', value.lower())
    match = re.fullmatch(r'([a-z][a-z0-9_]*)(?:\(\d+(?:,\d+)?\))?', normalized)
    if match:
        for family, names in _FAMILIES.items():
            if match[1] in names:
                return normalized, family
    return normalized, None


def assess_types(source_type, target_type, mode='compatible'):
    """Return an unverified informational or warning assessment for one pair."""
    if mode not in ('compatible', 'exact'):
        raise ValueError('Select compatible or exact type assessment')
    source, sf = _scalar(source_type)
    target, tf = _scalar(target_type)
    assessment, severity = 'unknown', 'info'
    if sf is not None and tf is not None:
        if source == target:
            assessment = 'exact'
        elif sf == tf:
            assessment = 'potentially_compatible'
            severity = 'warning' if mode == 'exact' else 'info'
        else:
            assessment, severity = 'requires_review', 'warning'
    return {'assessment': assessment, 'severity': severity, 'verified': False,
            'source_type': source_type, 'target_type': target_type,
            'limitation': 'Metadata only; does not prove compatibility, join safety or a safe cast'}


def validate_descriptor(value, depth=0, budget=None):
    """Version 1 native evidence, with fixed keys, depth and total node limits."""
    budget = [0] if budget is None else budget
    budget[0] += 1
    if depth > 4 or budget[0] > 64 or not isinstance(value, dict):
        raise ValueError('Invalid native type descriptor')
    if set(value) - {'schema_version', 'native', 'family', 'parameters', 'children', 'name'} or not {'schema_version', 'native', 'family'} <= set(value):
        raise ValueError('Invalid native type descriptor')
    if type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('Invalid native type descriptor')
    if not isinstance(value['family'], str) or value['family'] not in {'string', 'int64', 'float64', 'decimal', 'boolean', 'date', 'timestamp', 'binary', 'array', 'map', 'struct', 'unknown'}:
        raise ValueError('Invalid native type descriptor')
    if not isinstance(value['native'], str) or not 1 <= len(value['native']) <= 1024:
        raise ValueError('Invalid native type descriptor')
    if 'name' in value and (not isinstance(value['name'], str) or re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,127}', value['name']) is None):
        raise ValueError('Invalid native type descriptor')
    parameters = value.get('parameters', {})
    if not isinstance(parameters, dict) or set(parameters) - {'precision', 'scale', 'length'} or any(type(v) is not int or not 0 <= v <= 65535 for v in parameters.values()):
        raise ValueError('Invalid native type descriptor')
    children = value.get('children', [])
    if not isinstance(children, list) or len(children) > 32:
        raise ValueError('Invalid native type descriptor')
    for child in children:
        validate_descriptor(child, depth + 1, budget)


def native_descriptor(native, family, *, children=None):
    """Retain upstream spelling; do not claim the grammar has been verified."""
    result = {'schema_version': 1, 'native': native, 'family': family}
    match = re.fullmatch(r'(?i)(?:decimal|numeric)\((\d+),\s*(\d+)\)', native) if isinstance(native, str) else None
    if match:
        result['parameters'] = {'precision': int(match[1]), 'scale': int(match[2])}
    if children:
        result['children'] = children
    validate_descriptor(result)
    return result


def assess_native_types(source, target):
    """Describe fidelity differences without declaring native equivalence."""
    assessment = 'unknown'
    if source is not None and target is not None:
        validate_descriptor(source)
        validate_descriptor(target)
        assessment = 'unverified_match' if source == target else 'requires_review'
    return {'assessment':assessment, 'severity':'warning' if assessment=='requires_review' else 'info',
            'source':source,'target':target,'verified':False,
            'limitation':'Native spelling, parameters and nesting are advisory evidence; matching descriptors do not prove native equivalence'}
