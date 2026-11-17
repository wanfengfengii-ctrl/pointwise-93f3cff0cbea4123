from cohorts.models import validate_model, ModelVersion, InvalidModel
from cohorts.selection import select_revisions
from cohorts.binding import bind_cohort
from observations.repository import ReadingRepository
from archive.codec import encode_payload
from archive.publication import ArtifactDraft, publish_artifact
from archive.reading import read_artifact


def save_model(db, specification, failure_hook=None):
    model = validate_model(specification)
    with db.transaction() as c:
        row = c.execute('SELECT artifact FROM models WHERE name=? AND rev=?',
                        (model.name, model.rev)).fetchone()
        if row is not None:
            node = read_artifact(db, row[0])
            if node['kind'] != 'model' or encode_payload(node['payload']) != encode_payload(model.to_payload()):
                raise InvalidModel('immutable model version conflict')
            identity = row[0]
        else:
            identity = publish_artifact(c, ArtifactDraft('model', model.to_payload()), failure_hook)
            c.execute('INSERT INTO models VALUES (?,?,?)', (model.name, model.rev, identity))
    return identity


def freeze_cohort(db, model_id, members, failure_hook=None):
    with db.transaction() as c:
        node = read_artifact(db, model_id)
        if node['kind'] != 'model':
            raise InvalidModel('expected a registered model')
        model = ModelVersion.from_payload(node['payload'])
        selected = select_revisions(ReadingRepository(c), members)
        cohort = bind_cohort(model_id, model, selected)
        identity = publish_artifact(c, ArtifactDraft('cohort', cohort.to_payload(),
                                                     (model_id,)), failure_hook)
    return identity
