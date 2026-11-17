from archive.codec import decode_payload, payload_digest
from archive.exporting import build_export_bundle


class UnknownArtifact(KeyError):
    pass


class CorruptArtifact(ValueError):
    pass


def read_artifact(db, artifact_id):
    connection = db.connect()
    active, cache = set(), {}

    def visit(identity, root=False):
        if identity in active:
            raise CorruptArtifact('cycle in artifact graph')
        if identity in cache:
            return cache[identity]
        row = connection.execute(
            'SELECT c.kind,b.body,b.digest FROM catalog c LEFT JOIN blobs b ON b.id=c.id '
            'WHERE c.id=?', (identity,)).fetchone()
        if row is None:
            if root:
                raise UnknownArtifact(identity)
            raise CorruptArtifact('missing artifact parent')
        kind, body, digest = row
        try:
            if body is None or payload_digest(body) != digest or digest != identity:
                raise ValueError('artifact digest mismatch')
            envelope = decode_payload(body)
            if set(envelope) != {'kind', 'payload', 'parents'} or envelope['kind'] != kind:
                raise ValueError('artifact envelope mismatch')
            parents = envelope['parents']
            if not isinstance(parents, list) or any(type(p) is not str for p in parents):
                raise ValueError('invalid parent identities')
            edges = list(connection.execute(
                'SELECT position,parent FROM edges WHERE child=? ORDER BY position', (identity,)))
            if edges != list(enumerate(parents)):
                raise ValueError('artifact parent graph mismatch')
        except (ValueError, TypeError, KeyError) as exc:
            raise CorruptArtifact(str(exc)) from exc
        active.add(identity)
        node = {'id': identity, 'kind': kind, 'payload': envelope['payload'],
                'parents': [visit(p) for p in parents]}
        active.remove(identity)
        cache[identity] = node
        return node

    # A read transaction fixes the graph for the whole traversal.
    if connection.in_transaction:
        return visit(artifact_id, True)
    connection.execute('BEGIN')
    try:
        result = visit(artifact_id, True)
        connection.execute('COMMIT')
        return result
    except BaseException:
        connection.execute('ROLLBACK')
        raise


def export_artifact(db, report_id):
    return build_export_bundle(read_artifact(db, report_id))
