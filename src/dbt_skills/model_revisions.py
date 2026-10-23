"""Review and operator-approved replacement of unchanged generated model pairs."""
from copy import deepcopy
import difflib
import hashlib
import os
from pathlib import Path
import stat
import tempfile

from .model_drafts import DraftError, _bounded, _config, _digest, _file_hash, _target, prepare_model
from .model_validation import validate_applied


def _hash(content):
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def _changes(base, proposed):
    old, new = base['files'], proposed['files']
    if len(old) != 2 or len(new) != 2 or [f['path'] for f in old] != [f['path'] for f in new]:
        raise DraftError('Revision paths must match the original generated pair')
    result = []
    for before, after in zip(old, new):
        if after['operation'] != 'create' or not isinstance(after['content'], str) or len(after['content'].encode('utf-8')) > 65536:
            raise DraftError('Revision requires two bounded generated files')
        result.append({'path':after['path'], 'operation':'replace', 'before_sha256':_hash(before['content']),
                       'after_sha256':_hash(after['content']),
                       'diff':''.join(difflib.unified_diff(before['content'].splitlines(keepends=True), after['content'].splitlines(keepends=True), fromfile=before['path'], tofile=after['path']))})
    return result


def prepare_revision(project, policy_path, catalog, base, request, *, snapshot=None, context_id=None):
    if validate_applied(project, base)['status'] != 'passed':
        raise DraftError('Base draft, files or evidence changed; revision requires an unchanged validated generated model')
    proposed = prepare_model(project, policy_path, catalog, request, snapshot=snapshot, context_id=context_id,
                             _replacement_paths=[f['path'] for f in base['files']])
    if proposed['status'] != 'pending_review':
        return proposed
    files = _changes(base, proposed)
    if all(f['before_sha256'] == f['after_sha256'] for f in files):
        return {'status':'needs_clarification','questions':['The requested revision does not change generated files']}
    result = {'schema_version':1, 'kind':'model_revision', 'status':'pending_review',
              'base':deepcopy(base), 'proposed':proposed, 'files':files,
              'limitations':['Only unchanged previously generated SQL/YAML pairs may be revised',
                             'Two file replacements are not atomic; interrupted operations require inspection',
                             'Concurrent hostile filesystem mutation is outside the local operator contract',
                             'No warehouse validation, approval or file writes occur during preparation']}
    result['revision_id'] = _digest(result)
    _bounded(result)
    return result


def _cleanup(path):
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass  # Never expose filesystem exception details during cleanup.


def _stage(target, content, mode):
    fd, name = tempfile.mkstemp(prefix='.dbt-skills-revision-', suffix='.tmp', dir=target.parent)
    path = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content.encode('utf-8'))
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(path, mode)
        return path
    except BaseException:
        _cleanup(path)
        raise


def apply_revision(project, revision, approved_digest):
    try:
        _bounded(revision)
        if (revision['kind'] != 'model_revision' or revision['schema_version'] != 1 or revision['status'] != 'pending_review'
                or revision['revision_id'] != approved_digest or _digest({k:v for k,v in revision.items() if k != 'revision_id'}) != approved_digest):
            raise DraftError('Approval must match the complete reviewed revision digest')
        base, proposed = revision['base'], revision['proposed']
        if revision['files'] != _changes(base, proposed):
            raise DraftError('Revision changes do not match the sealed drafts')
        if validate_applied(project, base)['status'] != 'passed':
            raise DraftError('Base files or evidence changed; regenerate and review the revision')
        checks = validate_applied(project, proposed)['checks']
        if any(c['status'] != 'passed' for c in checks if c['check'] != 'applied_files'):
            raise DraftError('Proposed model contract or evidence is invalid')
        paths, _ = _config(project)
        targets = [_target(project, f['path'], paths, allow_existing=True) for f in revision['files']]
    except (KeyError, TypeError, ValueError, OSError) as error:
        if isinstance(error, DraftError):
            raise
        raise DraftError('Invalid model revision or unavailable inputs') from None
    staged, replaced, modes = [], [], []
    try:
        for target, after in zip(targets, proposed['files']):
            mode = stat.S_IMODE(target.stat().st_mode)
            modes.append(mode)
            staged.append(_stage(target, after['content'], mode))
        if validate_applied(project, base)['status'] != 'passed':
            raise DraftError('Base changed while staging revision')
        for index, (target, temporary, change) in enumerate(zip(targets, staged, revision['files'])):
            _target(project, change['path'], paths, allow_existing=True)
            if _file_hash(target) != change['before_sha256']:
                raise DraftError('Revision target changed before replacement')
            os.replace(temporary, target)
            replaced.append(index)
        if validate_applied(project, proposed)['status'] != 'passed':
            raise DraftError('Revised model failed local validation')
    except (OSError, ValueError, RuntimeError):
        rollback_complete = True
        for index in reversed(replaced):
            rollback = None
            try:
                change = revision['files'][index]
                _target(project, change['path'], paths, allow_existing=True)
                if _file_hash(targets[index]) != change['after_sha256']:
                    rollback_complete = False
                    continue
                rollback = _stage(targets[index], base['files'][index]['content'], modes[index])
                os.replace(rollback, targets[index])
            except (OSError, ValueError, RuntimeError):
                rollback_complete = False
            finally:
                if rollback is not None:
                    _cleanup(rollback)
        raise DraftError('Revision failed; replaced files restored; inspect workspace before continuing' if rollback_complete else 'Revision failed; rollback incomplete, inspect workspace before continuing') from None
    finally:
        for temporary in staged:
            _cleanup(temporary)
    return {'status':'replaced','revision_id':approved_digest,'draft_id':proposed['draft_id'],
            'paths':[f['path'] for f in revision['files']], 'warehouse_validated':False}


def main(argv=None):
    import argparse
    import json
    import sys
    from .catalog import _document, load_catalog
    from .project import discover_project

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'apply'])
    parser.add_argument('--project-dir', required=True)
    for name in ('base-draft', 'request', 'policy', 'catalog-config', 'target-path', 'revision', 'approve'):
        parser.add_argument('--' + name)
    args = parser.parse_args(argv)
    try:
        project = discover_project(args.project_dir, target_path=args.target_path)
        if args.command == 'prepare':
            if not all((args.base_draft, args.request, args.policy, args.catalog_config)) or args.approve is not None:
                raise DraftError('Prepare requires base draft, request, policy and catalog configuration')
            base, _ = _document(project.root / args.base_draft)
            request, _ = _document(project.root / args.request)
            result = prepare_revision(project, project.root / args.policy, load_catalog(project.root / args.catalog_config), base, request)
        else:
            if not args.revision or not args.approve:
                raise DraftError('Apply requires a revision and explicit reviewed digest')
            revision, _ = _document(project.root / args.revision)
            result = apply_revision(project, revision, args.approve)
        print(json.dumps(result, indent=2))
        return 2 if result['status'] == 'needs_clarification' else 0
    except (ValueError, OSError, RuntimeError, TypeError, KeyError):
        print('Cannot process revision: verify project, unchanged base, inputs and reviewed digest; inspect workspace after a failed apply', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
