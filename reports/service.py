from analysis.representation import JointTrajectory
from reports.requests import normalize_requests
from reports.contrasts import compile_contrasts, evaluate_contrasts
from reports.results import JointReport
from archive.publication import ArtifactDraft, publish_artifact
from archive.reading import read_artifact


def make_report(db, analysis_id, requests, failure_hook=None):
    with db.transaction() as c:
        node = read_artifact(db, analysis_id)
        if node['kind'] != 'analysis':
            raise ValueError('report requires a fixed analysis')
        trajectory = JointTrajectory.from_payload(node['payload']['trajectory'])
        specifications = normalize_requests(requests, trajectory.targets)
        contrasts = compile_contrasts(trajectory, specifications)
        statuses, estimates, covariance = evaluate_contrasts(trajectory, contrasts)
        result = JointReport(specifications, statuses, estimates, covariance)
        payload = {'analysis_id': analysis_id, 'result': result.to_payload()}
        identity = publish_artifact(c, ArtifactDraft('report', payload, (analysis_id,)),
                                    failure_hook)
    return identity
