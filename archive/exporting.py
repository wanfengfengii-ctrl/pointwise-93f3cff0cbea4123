from archive.codec import encode_payload, decode_payload


class InvalidExport(ValueError):
    pass


def build_export_bundle(report):
    expected = ('report', 'analysis', 'cohort', 'model')
    chain, node = [], report
    for index, kind in enumerate(expected):
        if node.get('kind') != kind or not isinstance(node.get('payload'), dict):
            raise InvalidExport('artifact chain type mismatch')
        chain.append(node)
        parents = node.get('parents')
        if not isinstance(parents, list) or len(parents) != (0 if index == 3 else 1):
            raise InvalidExport('artifact chain is not closed')
        if index != 3:
            node = parents[0]
    r, a, c, m = chain
    if (r['payload'].get('analysis_id') != a['id']
            or a['payload'].get('cohort_id') != c['id']
            or c['payload'].get('model_id') != m['id']
            or c['payload'].get('model') != m['payload']):
        raise InvalidExport('artifact binding mismatch')
    for key, payload in (('members', c['payload']),
                         ('trajectory', a['payload']),
                         ('result', r['payload'])):
        if key not in payload:
            raise InvalidExport('incomplete fixed payload')
    bundle = {'version': 1, 'report_id': r['id'],
              'model': m['payload'], 'observations': c['payload']['members'],
              'trajectory': a['payload']['trajectory'],
              'requests': r['payload']['result']['requests'],
              'result': r['payload']['result'],
              'lineage': [{'id': n['id'], 'kind': n['kind'],
                           'parents': [p['id'] for p in n['parents']]}
                          for n in reversed(chain)]}
    return decode_payload(encode_payload(bundle))


def run_demo(sample_path, database_path):
    import json
    from fractions import Fraction
    from pathlib import Path
    from archive.database import Database
    from archive.reading import read_artifact, export_artifact
    from observations.service import save_readings
    from cohorts.service import save_model, freeze_cohort
    from analysis.service import analyze
    from reports.service import make_report

    path = Path(database_path)
    if path.exists():
        raise ValueError('demo requires a new database path')
    sample = json.loads(Path(sample_path).read_text(encoding='utf-8'))
    with Database(path) as db:
        mid = save_model(db, sample['model'])
        save_readings(db, sample['readings'])
        members = [(r['measurement_id'], r['rev']) for r in sample['readings']]
        cohort = freeze_cohort(db, mid, members)
        analysis = analyze(db, cohort, sample['targets'])
        old = make_report(db, analysis, sample['requests'])
        old_export = encode_payload(export_artifact(db, old))
        correction = sample['correction']
        save_readings(db, [correction])
        corrected_members = [(identity, correction['rev'] if identity == correction['measurement_id'] else rev)
                             for identity, rev in members]
        new_cohort = freeze_cohort(db, mid, corrected_members)
        new_analysis = analyze(db, new_cohort, sample['targets'])
        new = make_report(db, new_analysis, sample['requests'])
        db.initialize()
    with Database(path) as db:
        old_value = read_artifact(db, old)['payload']['result']['estimates'][0]
        new_value = read_artifact(db, new)['payload']['result']['estimates'][0]
        if old_value != Fraction(sample['expected']['old']) or new_value != Fraction(sample['expected']['corrected']):
            raise AssertionError('day sample result differs from independent straight-line expectation')
        evidence_unchanged = encode_payload(export_artifact(db, old)) == old_export
        if not evidence_unchanged:
            raise AssertionError('old fixed evidence changed')
        actual = {'old': str(old_value), 'corrected': str(new_value)}
        record = {'case_id': 'v7.correction_snapshot',
                  'input': {'readings': sample['readings'], 'correction': correction},
                  'expected': sample['expected'], 'actual': actual,
                  'downstream_expected': {'old_evidence_unchanged': True},
                  'downstream_actual': {'old_evidence_unchanged': evidence_unchanged},
                  'code_paths': ['observations/service.py', 'cohorts/service.py',
                                 'analysis/service.py', 'reports/service.py',
                                 'archive/reading.py', 'archive/exporting.py'],
                  'oracle': 'Zero noise straight line: x(2)=2*x(1)-x(0); canonical old bundle equality.'}
        print('POINTWISE_SCENARIO ' + json.dumps(record, ensure_ascii=False, sort_keys=True))
        print(encode_payload(export_artifact(db, old)))
        return actual


def main():
    import argparse
    import tempfile
    from pathlib import Path
    parser = argparse.ArgumentParser(description='Run a fixed monitoring workday and export old evidence')
    parser.add_argument('--demo', required=True, metavar='SAMPLE_JSON')
    parser.add_argument('--db', metavar='NEW_DATABASE_PATH')
    args = parser.parse_args()
    if args.db:
        run_demo(args.demo, args.db)
    else:
        with tempfile.TemporaryDirectory(prefix='riverbend-demo-') as temporary:
            run_demo(args.demo, Path(temporary) / 'day.sqlite')


if __name__ == '__main__':
    main()
