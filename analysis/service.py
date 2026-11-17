from cohorts.binding import FrozenCohort
from analysis.dynamics import build_trajectory_design
from analysis.inference import infer_joint_trajectory
from archive.publication import ArtifactDraft, publish_artifact
from archive.reading import read_artifact


def analyze(db, cohort_id, targets, failure_hook=None):
    with db.transaction() as c:
        node = read_artifact(db, cohort_id)
        if node['kind'] != 'cohort':
            raise ValueError('analysis requires a frozen cohort')
        cohort = FrozenCohort.from_payload(node['payload'])
        design = build_trajectory_design(cohort, targets)
        trajectory = infer_joint_trajectory(design)
        payload = {'cohort_id': cohort_id, 'trajectory': trajectory.to_payload()}
        identity = publish_artifact(c, ArtifactDraft('analysis', payload, (cohort_id,)),
                                    failure_hook)
    return identity
