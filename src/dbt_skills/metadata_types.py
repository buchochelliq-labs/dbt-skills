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
