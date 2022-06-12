from dataclasses import dataclass


@dataclass
class JobCoverageEntity:
    id: str
    name: str
    coverage: float


@dataclass
class JobScoreEntity:
    id: str
    name: str
    score: float


@dataclass
class ProjectDetailEntity:
    name: str
    id: str
    merge_requests: int
    test_job: JobCoverageEntity
    pylint_job: JobScoreEntity
    bandit_job: JobScoreEntity
    safety_job: JobScoreEntity


@dataclass
class ConfigurationEntity:
    gitlab_username: str
    gitlab_token: str
    gitlab_url: str
    influx_url: str
    influx_token: str
    influx_org: str
