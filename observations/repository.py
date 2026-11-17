from archive.codec import encode_payload, decode_payload
from observations.revisions import MeasurementRevision


class ReadingRepository:
    def __init__(self, connection):
        self.connection = connection

    def get_revision(self, measurement_id, rev):
        row = self.connection.execute(
            'SELECT payload FROM revisions WHERE measurement_id=? AND rev=?',
            (measurement_id, rev)).fetchone()
        if row is None:
            raise KeyError((measurement_id, rev))
        item = MeasurementRevision.from_payload(decode_payload(row[0]))
        if item.identity != (measurement_id, rev):
            raise ValueError('corrupt reading identity')
        return item

    def get_heads(self):
        return dict(self.connection.execute('SELECT measurement_id,rev FROM heads'))

    def apply_plan(self, plan):
        if not self.connection.in_transaction:
            raise RuntimeError('revision writes require a transaction')
        for item in plan.accepted:
            self.connection.execute('INSERT INTO revisions VALUES (?,?,?)',
                                    (*item.identity, encode_payload(item.to_payload())))
            self.connection.execute(
                'INSERT INTO heads VALUES (?,?) ON CONFLICT(measurement_id) '
                'DO UPDATE SET rev=excluded.rev WHERE excluded.rev>heads.rev',
                item.identity)
