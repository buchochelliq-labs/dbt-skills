"""Operator-only, digest-bound acceptance of reviewed local context proposals.

Protects against stale bases and cooperating writers. It does not promise race
safety against a hostile process replacing directories during acceptance. The
review digest binds content, not the identity or authority of the operator.
"""
import argparse
from copy import deepcopy
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile

from .catalog import _document, _raw
from .context_limits import check_bounds
from .business_context import validate_business_context
from .design_decisions import validate_decisions


class ContextUpdateError(ValueError):
    """Static failure diagnostic, safe to return without input details."""


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def _digest(value):
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _validate(document):
    check_bounds(document)
    if not isinstance(document, dict):
        raise ValueError
    if document.get('kind') == 'business_context':
        validate_business_context(document)
    elif document.get('kind') == 'design_decisions':
        validate_decisions(document)
    else:
        raise ValueError


def _review_diff(before, after):
    # Canonical ordering with stable indentation makes the whole review readable.
    def lines(value):
        return (json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2, allow_nan=False) + '\n').splitlines(keepends=True)
    return ''.join(difflib.unified_diff(lines(before) if before is not None else [], lines(after),
                                      fromfile='base', tofile='proposed'))


def prepare_update(loaded, document):
    """Prepare a bounded review payload without reading or writing any files."""
    try:
        _validate(document)
        base = None
        if loaded is not None:
            if not isinstance(loaded, dict) or set(loaded) != {'document', 'provenance'}:
                raise ValueError
            _validate(loaded['document'])
            base = loaded['provenance']
            if (not isinstance(base, dict) or set(base) != {'document', 'sha256'} or
                    not isinstance(base['document'], str) or not Path(base['document']).is_absolute() or
                    '..' in Path(base['document']).parts or not isinstance(base['sha256'], str) or
                    re.fullmatch(r'[a-f0-9]{64}', base['sha256']) is None or
                    loaded['document']['kind'] != document['kind'] or loaded['document'] == document):
                raise ValueError
        proposal = {'schema_version': 1, 'base': deepcopy(base), 'proposed_document': deepcopy(document),
                    'review_diff': _review_diff(loaded['document'] if loaded else None, document)}
        proposal['proposal_sha256'] = _digest(proposal)
        check_bounds(proposal)
        return proposal
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        raise ContextUpdateError('context_update_not_saved') from None


def _target(root, selected):
    root = Path(root).absolute()
    selected = Path(selected)
    if '..' in root.parts or '..' in selected.parts:
        raise ValueError
    target = selected if selected.is_absolute() else root / selected
    if target == root or not target.is_relative_to(root):
        raise ValueError
    # Check every existing component, including root ancestors, without resolving
    # links away. Require a regular target and real parent directories.
    for item in reversed((target, *target.parents)):
        try:
            mode = item.lstat().st_mode
        except FileNotFoundError:
            if item != target:
                raise ValueError
            continue
        if stat.S_ISLNK(mode) or (item == target and not stat.S_ISREG(mode)) or (item != target and not stat.S_ISDIR(mode)):
            raise ValueError
    return target


def _current(target):
    if not target.exists():
        return None
    document, revision = _document(target)
    return {'document': document, 'provenance': {'document': str(target), 'sha256': revision}}


def accept_update(root, selected, proposal, *, accepted_digest):
    """Save only an exact reviewed proposal to an operator-selected project path."""
    lock_fd = None
    lock_path = temporary = None
    try:
        check_bounds(proposal)
        if (not isinstance(proposal, dict) or set(proposal) != {'schema_version', 'base', 'proposed_document', 'review_diff', 'proposal_sha256'} or
                type(proposal['schema_version']) is not int or proposal['schema_version'] != 1 or
                not isinstance(accepted_digest, str) or re.fullmatch(r'[a-f0-9]{64}', accepted_digest) is None or
                proposal['proposal_sha256'] != accepted_digest or
                _digest({k: v for k, v in proposal.items() if k != 'proposal_sha256'}) != accepted_digest):
            raise ValueError
        target = _target(root, selected)
        lock_path = target.with_name(target.name + '.lock')
        lock_fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        current = _current(target)
        if proposal['base'] != (current['provenance'] if current else None):
            raise ValueError
        # Reconstruct the complete payload from the current raw file. A rehashed
        # fake diff or redirected base must not pass merely by knowing SHA256.
        if prepare_update(current, proposal['proposed_document']) != proposal:
            raise ValueError
        mode = stat.S_IMODE(target.stat().st_mode) if current else 0o600
        fd, temporary = tempfile.mkstemp(prefix='.' + target.name + '.', dir=target.parent)
        raw = (json.dumps(proposal['proposed_document'], sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + '\n').encode()
        with os.fdopen(fd, 'wb') as stream:
            if hasattr(os, 'fchmod'):
                os.fchmod(stream.fileno(), mode)
            else:
                os.chmod(temporary, mode)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        _target(root, selected)
        if current:
            if hashlib.sha256(_raw(target)).hexdigest() != current['provenance']['sha256']:
                raise ValueError
            os.replace(temporary, target)
            temporary = None
        else:
            # Hard linking gives atomic create-only semantics: never clobber a
            # target created since the base check, even by an uncooperative writer.
            os.link(temporary, target)
        directory_synced = False
        try:
            directory_fd = os.open(target.parent, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
            try:
                os.fsync(directory_fd)
                directory_synced = True
            finally:
                os.close(directory_fd)
        except OSError:
            # Publication already succeeded. Directory durability is unavailable
            # on some platforms; never falsely report that no file was saved.
            pass
        return {'status': 'saved', 'document': str(target), 'sha256': hashlib.sha256(raw).hexdigest(),
                'refresh_required': True, 'directory_synced': directory_synced}
    except (ValueError, TypeError, KeyError, OSError, RecursionError):
        raise ContextUpdateError('context_update_not_saved') from None
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except OSError:
                pass
        if lock_fd is not None:
            try:
                os.close(lock_fd)
            except OSError:
                pass
            try:
                os.unlink(lock_path)
            except OSError:
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-dir', required=True)
    parser.add_argument('--target', required=True)
    parser.add_argument('--proposal', required=True)
    parser.add_argument('--accept-sha256', required=True)
    args = parser.parse_args(argv)
    try:
        proposal, _ = _document(Path(args.proposal))
        result = accept_update(args.project_dir, args.target, proposal, accepted_digest=args.accept_sha256)
        print(json.dumps(result))
        return 0
    except (ValueError, OSError, RuntimeError, TypeError, KeyError):
        print(json.dumps({'status': 'error', 'code': 'context_update_not_saved'}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
