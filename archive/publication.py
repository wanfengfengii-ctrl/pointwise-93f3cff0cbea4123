from dataclasses import dataclass
from archive.codec import encode_payload, decode_payload, payload_digest


@dataclass(frozen=True)
class ArtifactDraft:
    kind: str
    payload: dict
    parents: tuple = ()


def publish_artifact(connection, draft, failure_hook=None):
    if not connection.in_transaction:
        raise RuntimeError('publication requires caller transaction')
    if draft.kind not in {'model', 'cohort', 'analysis', 'report'}:
        raise ValueError('unknown artifact kind')
    for parent in draft.parents:
        row = connection.execute('SELECT id FROM catalog WHERE id=?', (parent,)).fetchone()
        if row is None:
            raise ValueError('unknown artifact parent')
    body = encode_payload({'kind': draft.kind, 'payload': draft.payload,
                           'parents': list(draft.parents)})
    identity = payload_digest(body)
    row = connection.execute('SELECT body,digest FROM blobs WHERE id=?', (identity,)).fetchone()
    if row is not None:
        edge_ids = [r[0] for r in connection.execute(
            'SELECT parent FROM edges WHERE child=? ORDER BY position', (identity,))]
        catalog = connection.execute('SELECT kind FROM catalog WHERE id=?', (identity,)).fetchone()
        if (row != (body, identity) or catalog != (draft.kind,)
                or edge_ids != list(draft.parents)):
            raise ValueError('existing artifact is incomplete or corrupt')
        decode_payload(row[0])
        return identity
    connection.execute('INSERT INTO blobs VALUES (?,?,?)', (identity, body, identity))
    for position, parent in enumerate(draft.parents):
        connection.execute('INSERT INTO edges VALUES (?,?,?)', (identity, position, parent))
    if failure_hook is not None:
        failure_hook('after_payload', identity)
    connection.execute('INSERT INTO catalog VALUES (?,?)', (identity, draft.kind))
    return identity
